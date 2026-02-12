from datetime import datetime
from . import db

class BlogPost(db.Model):
    __tablename__ = 'blog_posts'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), unique=True, nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    excerpt = db.Column(db.Text, nullable=True)
    featured_image = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='draft', nullable=False)  # published, draft, private
    published_at = db.Column(db.DateTime, nullable=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # SEO fields
    meta_title = db.Column(db.String(255), nullable=True)
    meta_description = db.Column(db.Text, nullable=True)
    meta_keywords = db.Column(db.Text, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    categories = db.relationship('BlogCategory', secondary='blog_post_categories', lazy='subquery', backref=db.backref('posts', lazy=True))
    tags = db.relationship('BlogTag', secondary='blog_post_tags', lazy='subquery', backref=db.backref('posts', lazy=True))
    author = db.relationship('User', backref='blog_posts', lazy=True)
    
    def __repr__(self):
        return f'<BlogPost {self.title}>'
    
    @property
    def is_published(self):
        """Check if post is published"""
        return self.status == 'published' and (self.published_at is None or self.published_at <= datetime.utcnow())


class BlogCategory(db.Model):
    __tablename__ = 'blog_categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('blog_categories.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    children = db.relationship('BlogCategory', backref=db.backref('parent', remote_side=[id]), lazy=True)
    
    def __repr__(self):
        return f'<BlogCategory {self.name}>'


class BlogTag(db.Model):
    __tablename__ = 'blog_tags'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<BlogTag {self.name}>'


# Association Tables
blog_post_categories = db.Table('blog_post_categories',
    db.Column('blog_post_id', db.Integer, db.ForeignKey('blog_posts.id'), primary_key=True),
    db.Column('blog_category_id', db.Integer, db.ForeignKey('blog_categories.id'), primary_key=True)
)

blog_post_tags = db.Table('blog_post_tags',
    db.Column('blog_post_id', db.Integer, db.ForeignKey('blog_posts.id'), primary_key=True),
    db.Column('blog_tag_id', db.Integer, db.ForeignKey('blog_tags.id'), primary_key=True)
)

