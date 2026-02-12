from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from models import db
from models.home_section import HomeSection
from models.product import Category
from utils.permissions import login_required

home_sections_bp = Blueprint('home_sections', __name__, url_prefix='/admin/home-sections')

@home_sections_bp.route('/')
@login_required
def list_sections():
    """List all home sections"""
    sections = HomeSection.query.order_by(HomeSection.display_order.asc()).all()
    return render_template('home_sections/list.html', sections=sections)

@home_sections_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_section():
    """Create a new home section"""
    if request.method == 'POST':
        try:
            title = request.form.get('title')
            subtitle = request.form.get('subtitle')
            section_type = request.form.get('section_type')
            category_id = request.form.get('category_id')
            item_limit = request.form.get('item_limit', 12)
            display_order = request.form.get('display_order', 0)
            
            if not title or not section_type:
                flash('Title and Section Type are required', 'error')
                return redirect(url_for('home_sections.create_section'))
            
            section = HomeSection(
                title=title,
                subtitle=subtitle,
                section_type=section_type,
                item_limit=int(item_limit),
                display_order=int(display_order),
                is_active=True
            )
            
            if section_type == 'category' and category_id:
                section.category_id = int(category_id)
            
            db.session.add(section)
            db.session.commit()
            
            flash('Section created successfully', 'success')
            return redirect(url_for('home_sections.list_sections'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating section: {str(e)}', 'error')
            return redirect(url_for('home_sections.create_section'))
            
    categories = Category.query.all()
    return render_template('home_sections/create.html', categories=categories)

@home_sections_bp.route('/edit/<int:section_id>', methods=['GET', 'POST'])
@login_required
def edit_section(section_id):
    """Edit home section"""
    section = HomeSection.query.get_or_404(section_id)
    
    if request.method == 'POST':
        try:
            section.title = request.form.get('title')
            section.subtitle = request.form.get('subtitle')
            section.section_type = request.form.get('section_type')
            category_id = request.form.get('category_id')
            section.item_limit = int(request.form.get('item_limit', 12))
            section.display_order = int(request.form.get('display_order', 0))
            
            if section.section_type == 'category' and category_id:
                section.category_id = int(category_id)
            else:
                section.category_id = None
                
            db.session.commit()
            flash('Section updated successfully', 'success')
            return redirect(url_for('home_sections.list_sections'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating section: {str(e)}', 'error')
            return redirect(url_for('home_sections.edit_section', section_id=section.id))
            
    categories = Category.query.all()
    return render_template('home_sections/create.html', section=section, categories=categories)

@home_sections_bp.route('/delete/<int:section_id>', methods=['POST'])
@login_required
def delete_section(section_id):
    """Delete home section"""
    section = HomeSection.query.get_or_404(section_id)
    try:
        db.session.delete(section)
        db.session.commit()
        flash('Section deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting section: {str(e)}', 'error')
        
    return redirect(url_for('home_sections.list_sections'))

@home_sections_bp.route('/toggle-status/<int:section_id>', methods=['POST'])
@login_required
def toggle_status(section_id):
    """Toggle section status"""
    section = HomeSection.query.get_or_404(section_id)
    try:
        section.is_active = not section.is_active
        db.session.commit()
        return jsonify({'success': True, 'is_active': section.is_active})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@home_sections_bp.route('/reorder', methods=['POST'])
@login_required
def reorder_sections():
    """Reorder sections"""
    try:
        data = request.json
        print("Reorder Data:", data) # Debugging log
        
        # Expecting a list of objects like: [{"id": 1, "order": 0}, {"id": 2, "order": 1}]
        # OR simple list of IDs in order: [1, 5, 3] which implies index = order
        
        if not data:
             return jsonify({'success': False, 'message': 'No data provided'}), 400

        # Handle list of IDs (simpler for drag and drop libraries often)
        if isinstance(data, list):
             for index, item in enumerate(data):
                 # If item is dict (id, order), use that. Else treat item as ID
                 if isinstance(item, dict):
                     section_id = item.get('id')
                     # order = item.get('order', index) # Use index as fallback or primary?
                     # Let's trust the index in the list as the order
                     section = HomeSection.query.get(section_id)
                     if section:
                         section.display_order = index
                 else:
                     # Treat item as ID
                     section = HomeSection.query.get(item)
                     if section:
                         section.display_order = index
             
             db.session.commit()
             return jsonify({'success': True})
        
        return jsonify({'success': False, 'message': 'Invalid data format'}), 400

    except Exception as e:
        print("Reorder Error:", e)
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
