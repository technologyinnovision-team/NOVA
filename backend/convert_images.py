import os
import sys
from app import app
from models import db
from models.product import Product, ProductImage, ProductVariation, Category
from utils.upload import convert_to_webp

def batch_convert():
    """
    Convert all images in uploads folder to WebP and update database references.
    """
    print("Starting batch conversion to WebP...")
    
    with app.app_context():
        base_dir = os.path.dirname(os.path.abspath(__file__))
        upload_folder = os.path.join(base_dir, 'uploads')
        
        if not os.path.exists(upload_folder):
            print("Uploads folder not found.")
            return

        converted_map = {}  # old_path -> new_path (relative to backend root, or just the stored DB string)

        # 1. Convert Files
        for root, dirs, files in os.walk(upload_folder):
            for file in files:
                if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                    full_path = os.path.join(root, file)
                    
                    # Skip if webp version already exists?
                    # No, we want to ensure everything uses webp.
                    
                    print(f"Converting: {full_path}")
                    new_path = convert_to_webp(full_path)
                    
                    if new_path != full_path:
                        # Construct relative paths as stored in DB
                        # DB paths usually start with /uploads/...
                        # root is something like .../backend/uploads/products
                        
                        rel_dir = os.path.relpath(root, base_dir) # e.g. uploads/products
                        old_rel = f"/{rel_dir}/{file}".replace('\\', '/')
                        new_filename = os.path.basename(new_path)
                        new_rel = f"/{rel_dir}/{new_filename}".replace('\\', '/')
                        
                        converted_map[old_rel] = new_rel
                        
                        # Verify file exists
                        if os.path.exists(new_path):
                            # Delete old file
                            try:
                                os.remove(full_path)
                                print(f"Deleted original: {full_path}")
                            except Exception as e:
                                print(f"Could not delete {full_path}: {e}")

        print(f"Converted {len(converted_map)} files.")

        # 2. Update Database
        if not converted_map:
            print("No files converted.")
            return

        print("Updating database records...")
        
        # Helper to update standard image queries
        def update_model_images(Model, field_name):
            count = 0
            records = Model.query.all()
            for record in records:
                current_url = getattr(record, field_name)
                if current_url and current_url in converted_map:
                    setattr(record, field_name, converted_map[current_url])
                    count += 1
            return count

        # ProductImage
        pi_count = update_model_images(ProductImage, 'image_url')
        print(f"Updated {pi_count} ProductImages.")

        # Category
        cat_count = update_model_images(Category, 'image_url')
        print(f"Updated {cat_count} Categories.")
        
        # ProductVariation
        var_count = update_model_images(ProductVariation, 'image_url')
        print(f"Updated {var_count} ProductVariations.")

        # Product Descriptions (Text search/replace)
        print("Updating Product descriptions...")
        desc_count = 0
        products = Product.query.all()
        for p in products:
            changed = False
            if p.description:
                for old_url, new_url in converted_map.items():
                    if old_url in p.description:
                        p.description = p.description.replace(old_url, new_url)
                        changed = True
            
            if p.short_description:
                 for old_url, new_url in converted_map.items():
                    if old_url in p.short_description:
                        p.short_description = p.short_description.replace(old_url, new_url)
                        changed = True
                        
            if changed:
                desc_count += 1
        print(f"Updated descriptions for {desc_count} products.")

        db.session.commit()
        print("Database update complete.")

if __name__ == "__main__":
    batch_convert()
