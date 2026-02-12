from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import db
from models.product import Category
from utils.permissions import login_required
from utils.validators import generate_slug

categories = Blueprint('categories', __name__, url_prefix='/admin/categories')

@categories.route('/')
@login_required
def list():
    """Category listing page"""
    categories_list = Category.query.order_by(Category.display_order, Category.name).all()
    return render_template('categories/list.html', categories=categories_list)

@categories.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Create category"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Category name is required.', 'error')
            return render_template('categories/form.html', parent_categories=get_parent_categories())
        
        category = Category(
            name=name,
            slug=request.form.get('slug', '').strip() or generate_slug(name),
            description=request.form.get('description', ''),
            parent_id=int(request.form.get('parent_id')) if request.form.get('parent_id') else None,
            display_order=int(request.form.get('display_order', 0) or 0)
        )
        
        db.session.add(category)
        db.session.commit()
        
        flash('Category created successfully!', 'success')
        return redirect(url_for('categories.list'))
    
    return render_template('categories/form.html', category=None, parent_categories=get_parent_categories())

@categories.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Edit category"""
    category = Category.query.get_or_404(id)
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Category name is required.', 'error')
            return render_template('categories/form.html', category=category, parent_categories=get_parent_categories())
        
        category.name = name
        category.slug = request.form.get('slug', '').strip() or generate_slug(name)
        category.description = request.form.get('description', '')
        category.parent_id = int(request.form.get('parent_id')) if request.form.get('parent_id') else None
        category.display_order = int(request.form.get('display_order', 0) or 0)
        
        db.session.commit()
        
        flash('Category updated successfully!', 'success')
        return redirect(url_for('categories.list'))
    
    return render_template('categories/form.html', category=category, parent_categories=get_parent_categories())

def get_parent_categories():
    """Get all categories for parent selection"""
    return Category.query.order_by(Category.name).all()

