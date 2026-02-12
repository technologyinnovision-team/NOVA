import math
import logging
from datetime import datetime, timedelta
from models import db
from models.order import Order
from models.pos import POSSellerProfile, POSInventory
from models.product import Product, ProductVariation

class FulfillmentService:
    # Coordinates for "Source China" (e.g., Shanghai/Guangzhou)
    # Using Guangzhou as a major shipping hub approximation: 23.1291° N, 113.2644° E
    CHINA_LAT = 23.1291
    CHINA_LON = 113.2644

    @staticmethod
    def calculate_distance(lat1, lon1, lat2, lon2):
        """
        Calculate the great circle distance between two points 
        on the earth (specified in decimal degrees) using Haversine formula.
        Returns distance in kilometers.
        """
        if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
            return float('inf')

        # Convert decimal degrees to radians 
        lon1, lat1, lon2, lat2 = map(math.radians, [float(lon1), float(lat1), float(lon2), float(lat2)])

        # Haversine formula 
        dlon = lon2 - lon1 
        dlat = lat2 - lat1 
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a)) 
        r = 6371 # Radius of earth in kilometers. Use 3956 for miles
        return c * r

    @staticmethod
    def find_nearest_eligible_sellers(order_id, limit=5):
        """
        Finds the nearest ACTIVE POS sellers who have ALL items in stock.
        Returns a list of (seller, distance) tuples, sorted by distance.
        """
        from utils.geocoding import GeocodingService

        order = Order.query.get(order_id)
        if not order or not order.shipping_address:
            return []
            
        # Get customer location
        cust_lat = order.shipping_address.get('latitude')
        cust_lon = order.shipping_address.get('longitude')
        
        # If no coords, attempt Geocoding
        if cust_lat is None or cust_lon is None:
            logging.info(f"Order {order.order_number}: No coordinates found, attempting geocoding.")
            formatted_addr = GeocodingService.format_address(order.shipping_address)
            lat, lon = GeocodingService.get_coordinates(formatted_addr)
            if lat and lon:
                cust_lat = lat
                cust_lon = lon
                # Save back to order (might need to update the JSON carefully)
                # Note: modifying a JSON field partially in some DBs is tricky, 
                # but SQLAlchemy usually handles full dict replacement.
                # We will update the dict in memory and flag modified.
                updated_addr = order.shipping_address.copy()
                updated_addr['latitude'] = lat
                updated_addr['longitude'] = lon
                order.shipping_address = updated_addr
                db.session.commit() # Save coords for future use
            else:
                logging.warning(f"Order {order.order_number}: Geocoding failed. Cannot calculate distance.")
        
        # 1. Get all Active POS Sellers
        active_sellers = POSSellerProfile.query.filter_by(is_active=True).all()
        
        eligible_sellers = []
        
        for seller in active_sellers:
            # 2. Check Stock for ALL items
            has_stock = True
            for item in order.items:
                # Find inventory record
                inventory = POSInventory.query.filter_by(
                    seller_id=seller.id,
                    product_id=item.product_id,
                    variation_id=item.variation_id
                ).first()
                
                required_qty = item.quantity
                
                # Available = Quantity - Reserved
                if not inventory or (inventory.quantity - inventory.reserved_quantity) < required_qty:
                    has_stock = False
                    break
            
            if has_stock:
                # 3. Calculate Distance
                dist = float('inf')
                if cust_lat is not None and cust_lon is not None:
                     dist = FulfillmentService.calculate_distance(
                        cust_lat, cust_lon, 
                        seller.latitude, seller.longitude
                    )
                
                # If distance matches (multiple sellers at same location or infinity), use ID as tiebreaker for consistency
                eligible_sellers.append((seller, dist))
        
        # 4. Sort by distance, then by seller ID for stability
        eligible_sellers.sort(key=lambda x: (x[1], x[0].id))
        
        return eligible_sellers[:limit]

    @staticmethod
    def assign_order(order_id):
        """
        Main entry point to assign an order.
        Tries to find nearest seller based on current attempts.
        """
        order = Order.query.get(order_id)
        if not order:
            return False, "Order not found"
            
        # Avoid re-assigning if already accepted or shipped
        if order.assignment_status in ['accepted', 'shipped']:
            return False, "Order already accepted or shipped"

        # Find candidates
        candidates = FulfillmentService.find_nearest_eligible_sellers(order_id, limit=20) # Increase limit for retries
        
        # Determine which candidate index to try next
        # If it's a fresh order, attempts=0, we pick index 0.
        # If it's a reassignment (rejected/timeout), attempts might be 1, so we pick index 1.
        current_attempt_index = order.assignment_attempts
        
        # If we ran out of eligible sellers
        if current_attempt_index >= len(candidates):
            logging.info(f"Order {order.order_number}: No more eligible sellers (Attempt {current_attempt_index}). Falling back to Admin.")
            return FulfillmentService.fallback_to_admin(order)

        best_seller_tuple = candidates[current_attempt_index]
        best_seller = best_seller_tuple[0] # (seller, distance)
        best_seller_dist = best_seller_tuple[1]
        
        # LOGIC CHECK: Is Buyer closer to China than to this Seller?
        # Only check if we have valid customer coordinates (implied if best_seller_dist is not inf)
        cust_lat = order.shipping_address.get('latitude')
        cust_lon = order.shipping_address.get('longitude')
        
        if cust_lat is not None and cust_lon is not None:
            dist_to_china = FulfillmentService.calculate_distance(cust_lat, cust_lon, FulfillmentService.CHINA_LAT, FulfillmentService.CHINA_LON)
            
            # If China is CLOSER (strictly less) than the proposed seller, assign to Admin.
            if dist_to_china < best_seller_dist:
                 logging.info(f"Order {order.order_number}: Buyer is closer to China ({dist_to_china:.2f}km) than nearest eligible seller ({best_seller_dist:.2f}km). Assigning to Admin.")
                 return FulfillmentService.fallback_to_admin(order)
        
        # Lock Stock
        try:
            for item in order.items:
                inventory = POSInventory.query.filter_by(
                    seller_id=best_seller.id,
                    product_id=item.product_id,
                    variation_id=item.variation_id
                ).first()
                if inventory:
                    inventory.reserved_quantity += item.quantity
            
            # Update Order
            order.fulfillment_source = 'pos'
            order.assigned_seller_id = best_seller.id
            order.assignment_status = 'assigned'
            order.assignment_attempts += 1 # Increment for NEXT time
            order.assignment_expiry = datetime.utcnow() + timedelta(hours=24) # 24 hour window
            
            # If seller has auto_accept
            if best_seller.auto_accept_orders:
                order.assignment_status = 'accepted'
                # Auto-accept: Reserved stock stays reserved until shipment
                
            db.session.commit()
            return True, f"Assigned to {best_seller.business_name} (Attempt {order.assignment_attempts})"
            
        except Exception as e:
            db.session.rollback()
            return False, f"Assignment failed: {str(e)}"

    @staticmethod
    def fallback_to_admin(order):
        """
        Assigns order to Admin Direct Fulfillment.
        Deducts Global/Admin Stock.
        """
        try:
            order.fulfillment_source = 'admin'
            order.assigned_seller_id = None
            order.assignment_status = 'assigned'
            
            # Deduct Global Stock (Admin Stock)
            out_of_stock_alerts = []
            for item in order.items:
                product_name_for_alert = item.product_name
                
                # Check Variation Stock first
                if item.variation_id:
                    variation = ProductVariation.query.get(item.variation_id)
                    
                    if variation and variation.manage_stock:
                        variation.stock_quantity -= item.quantity
                        if variation.stock_quantity <= 0:
                            variation.stock_quantity = 0
                            variation.stock_status = 'out_of_stock'
                            out_of_stock_alerts.append(f"Variation {variation.id} for {product_name_for_alert}")
                
                # Check Product Stock (Global)
                product_obj = Product.query.get(item.product_id)
                if product_obj and product_obj.manage_stock:
                     product_obj.stock_quantity -= item.quantity
                     if product_obj.stock_quantity <= 0:
                         product_obj.stock_quantity = 0
                         product_obj.stock_status = 'out_of_stock'
                         out_of_stock_alerts.append(f"Product: {product_obj.title}")
            
            db.session.commit()
            
            # TODO: trigger async email alerts for out_of_stock if any (same as original checkout.py)
            
            return True, "Assigned to Admin Direct Fulfillment"
        except Exception as e:
            db.session.rollback()
            return False, f"Admin fallback failed: {str(e)}"
