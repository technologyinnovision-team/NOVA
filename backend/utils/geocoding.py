import requests
import logging
import time

class GeocodingService:
    """
    Service to convert addresses to coordinates using OpenStreetMap (Nominatim).
    Please respect API usage policy (max 1 request/sec).
    """
    
    BASE_URL = "https://nominatim.openstreetmap.org/search"
    USER_AGENT = "BaileBelle_OrderSystem/1.0"

    @staticmethod
    def get_coordinates(address_string):
        """
        Get latitude and longitude for a given address string.
        Returns: (latitude, longitude) or (None, None) if failed.
        """
        if not address_string:
            return None, None
            
        try:
            params = {
                'q': address_string,
                'format': 'json',
                'limit': 1
            }
            
            headers = {
                'User-Agent': GeocodingService.USER_AGENT
            }
            
            # Respect rate limits
            # time.sleep(1) 
            
            response = requests.get(GeocodingService.BASE_URL, params=params, headers=headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    lat = float(data[0].get('lat'))
                    lon = float(data[0].get('lon'))
                    return lat, lon
                else:
                    logging.warning(f"Geocoding found no results for: {address_string}")
            else:
                logging.error(f"Geocoding API error: {response.status_code} - {response.text}")
                
        except Exception as e:
            logging.error(f"Geocoding exception: {str(e)}")
            
        return None, None

    @staticmethod
    def format_address(address_dict):
        """
        Helper to format address dict into a query string.
        """
        parts = [
            address_dict.get('address', ''),
            address_dict.get('city', ''),
            address_dict.get('state', ''),
            address_dict.get('zipCode', ''),
            address_dict.get('country', '')
        ]
        # Filter out empty parts
        return ", ".join([p for p in parts if p])
