from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, UTC
import json
from sqlalchemy import func, desc, Table, Column, Integer, ForeignKey, text
import os
from werkzeug.utils import secure_filename
import random
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration classes
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static/uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///lms.db'

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///lms.db'

# Initialize Flask app
app = Flask(__name__)

# Load configuration based on environment
if os.environ.get('FLASK_ENV') == 'production':
    app.config.from_object(ProductionConfig)
else:
    app.config.from_object(DevelopmentConfig)

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Define association tables
course_tags = db.Table('course_tags',
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)

course_prerequisites = db.Table('course_prerequisites',
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'), primary_key=True),
    db.Column('prerequisite_id', db.Integer, db.ForeignKey('course.id'), primary_key=True)
)

# Models
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    courses = db.relationship('Course', backref='category', lazy=True)

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), nullable=False)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now(UTC))
    enrollments = db.relationship('Enrollment', backref='user', lazy=True)
    reviews = db.relationship('Review', backref='user', lazy=True)
    activities = db.relationship('UserActivity', backref='user', lazy=True)
    test_attempts = db.relationship('TestAttempt', back_populates='user', lazy=True)

class UserActivity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.now(UTC))

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    difficulty_level = db.Column(db.String(20), default='Beginner')
    estimated_duration = db.Column(db.Float)  # in hours
    created_at = db.Column(db.DateTime, default=datetime.now(UTC))
    content_id = db.Column(db.Integer, db.ForeignKey('content.id'))
    prerequisites = db.Column(db.Text)  # Store as JSON string
    image_url = db.Column(db.String(255))  # Add image_url field
    is_published = db.Column(db.Boolean, default=False)
    tags = db.relationship('Tag', secondary=course_tags, lazy='subquery',
        backref=db.backref('courses', lazy=True))
    enrollments = db.relationship('Enrollment', backref='course', lazy=True)
    reviews = db.relationship('Review', backref='course', lazy=True)

    # Additional fields for better UI and formatting
    estimated_duration = db.Column(db.Float)  # in hours
    
    # Relationships
    prerequisites = db.relationship(
        'Course', 
        secondary='course_prerequisites',
        primaryjoin=(id == course_prerequisites.c.course_id),
        secondaryjoin=(id == course_prerequisites.c.prerequisite_id),
        backref=db.backref('dependent_courses', lazy='dynamic')
    )

    @property
    def average_rating(self):
        if not self.reviews:
            return 0
        return sum(review.rating for review in self.reviews) / len(self.reviews)

    @property
    def prerequisite_list(self):
        return json.loads(self.prerequisites) if self.prerequisites else []

class Content(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now(UTC))
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    courses = db.relationship('Course', backref='content', lazy=True)
    sections = db.relationship('ContentSection', backref=db.backref('parent_content', lazy=True), lazy=True, order_by='ContentSection.order')

class ContentSection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content_id = db.Column(db.Integer, db.ForeignKey('content.id'))
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text)
    order = db.Column(db.Integer, nullable=False)
    type = db.Column(db.String(20))  # 'text', 'video', 'quiz', etc.

class Enrollment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'))
    enrolled_at = db.Column(db.DateTime, default=datetime.now(UTC))
    progress = db.Column(db.Float, default=0.0)  # Percentage of completion
    last_accessed = db.Column(db.DateTime)
    completed_sections = db.Column(db.Text)  # Store as JSON string

    @property
    def completed_section_list(self):
        return json.loads(self.completed_sections) if self.completed_sections else []

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'))
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stars
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now(UTC))
    updated_at = db.Column(db.DateTime, onupdate=datetime.now(UTC))

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Routes
@app.route('/landing')
def landing():
    # Get latest courses
    latest_courses = Course.query.order_by(Course.created_at.desc()).limit(3).all()

    # Get stats
    total_courses = Course.query.count()
    total_users = User.query.count()
    total_enrollments = Enrollment.query.count()

    return render_template(
        'landing.html',
        latest_courses=latest_courses,
        total_courses=total_courses,
        total_users=total_users,
        total_enrollments=total_enrollments
    )

@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('landing'))
        
    # Get filter parameters
    category_id = request.args.get('category', type=int)
    difficulty = request.args.get('difficulty')
    sort_by = request.args.get('sort', 'newest')

    # Start with base query
    query = Course.query

    # Apply filters
    if category_id:
        query = query.filter_by(category_id=category_id)
    if difficulty:
        query = query.filter_by(difficulty_level=difficulty)

    # Apply sorting
    if sort_by == 'newest':
        query = query.order_by(Course.created_at.desc())
    elif sort_by == 'rating':
        # Note: This is a simplified sorting by rating
        # In a production environment, you might want to use a more sophisticated method
        query = query.order_by(Course.reviews.any().desc())
    elif sort_by == 'popular':
        # Sort by number of enrollments
        query = query.order_by(Course.enrollments.any().desc())

    # Get all courses
    courses = query.all()

    # Get all categories for the filter dropdown
    categories = Category.query.all()

    return render_template('index.html', courses=courses, categories=categories)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('register'))

        if password != confirm_password:
            flash('Passwords do not match')
            return redirect(url_for('register'))

        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()

        # Add registration activity
        activity = UserActivity(
            user_id=user.id,
            title='Account Created',
            description='You registered for an account'
        )
        db.session.add(activity)
        db.session.commit()

        flash('Registration successful! Please login.')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            
            # Add login activity
            activity = UserActivity(
                user_id=user.id,
                title='User Login',
                description='You logged into your account'
            )
            db.session.add(activity)
            db.session.commit()
            
            return redirect(url_for('dashboard'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    # Add logout activity
    activity = UserActivity(
        user_id=current_user.id,
        title='User Logout',
        description='You logged out of your account'
    )
    db.session.add(activity)
    db.session.commit()
    
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Get enrolled and completed courses
    enrolled_courses = current_user.enrollments
    completed_courses = [e for e in enrolled_courses if e.progress >= 100]
    
    # Calculate overall progress
    if enrolled_courses:
        overall_progress = sum(e.progress for e in enrolled_courses) / len(enrolled_courses)
    else:
        overall_progress = 0
    
    # Get recent activities with more details
    recent_activities = UserActivity.query.filter_by(user_id=current_user.id)\
        .order_by(UserActivity.timestamp.desc())\
        .limit(5)\
        .all()
    
    # Calculate achievements
    achievements = {
        'first_course': len(completed_courses) > 0,
        'course_master': len(completed_courses) >= 5,
        'perfect_score': any(e.progress == 100 for e in enrolled_courses),
        'community': len(current_user.reviews) >= 5
    }
    
    # Get learning streak
    today = datetime.now(UTC).date()
    streak = 0
    last_activity = UserActivity.query.filter_by(user_id=current_user.id)\
        .order_by(UserActivity.timestamp.desc())\
        .first()
    if last_activity:
        last_date = last_activity.timestamp.date()
        if last_date == today:
            streak = 1
            current_date = last_date - timedelta(days=1)
            while UserActivity.query.filter(
                UserActivity.user_id == current_user.id,
                func.date(UserActivity.timestamp) == current_date
            ).first():
                streak += 1
                current_date -= timedelta(days=1)
    
    # Get course recommendations based on completed courses
    completed_categories = [e.course.category_id for e in completed_courses if e.course.category_id]
    if completed_categories:
        recommended_courses = Course.query\
            .filter(Course.category_id.in_(completed_categories))\
            .filter(~Course.id.in_([e.course_id for e in enrolled_courses]))\
            .order_by(func.random())\
            .limit(3)\
            .all()
    else:
        recommended_courses = Course.query\
            .filter(~Course.id.in_([e.course_id for e in enrolled_courses]))\
            .order_by(func.random())\
            .limit(3)\
            .all()
    
    # Get learning statistics
    total_time_spent = 0
    for e in enrolled_courses:
        if e.last_accessed and e.enrolled_at:
            # Make sure both are timezone-aware
            if e.last_accessed.tzinfo is None:
                last_accessed = e.last_accessed.replace(tzinfo=UTC)
            else:
                last_accessed = e.last_accessed
                
            if e.enrolled_at.tzinfo is None:
                enrolled_at = e.enrolled_at.replace(tzinfo=UTC)
            else:
                enrolled_at = e.enrolled_at
                
            # Calculate time spent in hours
            time_spent = (last_accessed - enrolled_at).total_seconds() / 3600
            total_time_spent += time_spent
    
    stats = {
        'total_courses': len(enrolled_courses),
        'completed_courses': len(completed_courses),
        'overall_progress': overall_progress,
        'learning_streak': streak,
        'total_time_spent': round(total_time_spent, 1),
        'average_rating': round(
            sum(r.rating for r in current_user.reviews) / len(current_user.reviews)
            if current_user.reviews else 0,
            1
        )
    }
    
    return render_template('dashboard.html',
                         enrolled_courses=enrolled_courses,
                         completed_courses=completed_courses,
                         overall_progress=overall_progress,
                         recent_activities=recent_activities,
                         achievements=achievements,
                         stats=stats,
                         recommended_courses=recommended_courses)

@app.route('/course/<int:course_id>')
@login_required
def course_detail(course_id):
    course = db.session.get(Course, course_id)
    if not course:
        flash('Course not found', 'error')
        return redirect(url_for('index'))
    
    enrollment = Enrollment.query.filter_by(
        user_id=current_user.id,
        course_id=course_id
    ).first()
    return render_template('course_detail.html', course=course, enrollment=enrollment)

@app.route('/enroll/<int:course_id>')
@login_required
def enroll_course(course_id):
    course = db.session.get(Course, course_id)
    if not course:
        flash('Course not found', 'error')
        return redirect(url_for('index'))
        
    if not Enrollment.query.filter_by(user_id=current_user.id, course_id=course_id).first():
        enrollment = Enrollment(user_id=current_user.id, course_id=course_id)
        db.session.add(enrollment)
        
        # Add enrollment activity
        activity = UserActivity(
            user_id=current_user.id,
            title='Course Enrollment',
            description=f'You enrolled in {course.title}'
        )
        db.session.add(activity)
        db.session.commit()
        
        flash('Successfully enrolled in the course!')
    return redirect(url_for('course_detail', course_id=course_id))

# Admin routes
@app.route('/admin/content', methods=['GET', 'POST'])
@login_required
def manage_content():
    if not current_user.is_admin:
        flash('Access denied')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        title = request.form.get('title')
        content_text = request.form.get('content')
        
        # Create content
        new_content = Content(
            title=title,
            content=content_text,
            created_by=current_user.id
        )
        db.session.add(new_content)
        db.session.flush()  # Get content ID
        
        # Create course
        course = Course(
            title=title,
            description=f"Course for {title}",
            content_id=new_content.id
        )
        db.session.add(course)
        db.session.flush()  # Get course ID
        
        # Handle quiz creation if requested
        if request.form.get('add_quiz'):
            quiz = Quiz(
                course_id=course.id,
                title=request.form.get('quiz_title'),
                description=request.form.get('quiz_description'),
                time_limit=request.form.get('time_limit', type=int),
                passing_score=request.form.get('passing_score', type=int)
            )
            db.session.add(quiz)
            db.session.flush()  # Get quiz ID
            
            # Add questions
            question_count = 0
            while f'question_{question_count}' in request.form:
                question = QuizQuestion(
                    quiz_id=quiz.id,
                    question_text=request.form.get(f'question_{question_count}'),
                    question_type=request.form.get(f'question_type_{question_count}'),
                    points=request.form.get(f'points_{question_count}', type=int, default=1)
                )
                db.session.add(question)
                db.session.flush()  # Get question ID
                
                # Add options
                option_count = 0
                while f'option_{question_count}_{option_count}' in request.form:
                    option_text = request.form.get(f'option_{question_count}_{option_count}')
                    is_correct = request.form.get(f'correct_{question_count}') == str(option_count)
                    
                    option = QuizOption(
                        question_id=question.id,
                        option_text=option_text,
                        is_correct=is_correct
                    )
                    db.session.add(option)
                    db.session.flush()
                    
                    if is_correct:
                        question.correct_option_id = option.id
                    
                    option_count += 1
                
                question_count += 1
        
        # Handle test creation if requested
        if request.form.get('add_test'):
            test = Test(
                course_id=course.id,
                title=request.form.get('test_title'),
                description=request.form.get('test_description'),
                time_limit=request.form.get('test_time_limit', type=int),
                passing_score=request.form.get('test_passing_score', type=int)
            )
            db.session.add(test)
            db.session.flush()  # Get test ID
            
            # Add questions
            question_count = 0
            while f'test_question_{question_count}' in request.form:
                question_type = request.form.get(f'test_question_type_{question_count}')
                question = Question(
                    test_id=test.id,
                    text=request.form.get(f'test_question_{question_count}'),
                    type=question_type
                )
                db.session.add(question)
                db.session.flush()  # Get question ID
                
                if question_type in ['multiple_choice', 'true_false']:
                    option_count = 0
                    while f'test_option_{question_count}_{option_count}' in request.form:
                        option_text = request.form.get(f'test_option_{question_count}_{option_count}')
                        is_correct = request.form.get(f'test_correct_{question_count}') == str(option_count)
                        
                        option = Option(
                            question_id=question.id,
                            text=option_text
                        )
                        db.session.add(option)
                        db.session.flush()
                        
                        if is_correct:
                            question.correct_option = option.id
                        
                        option_count += 1
                elif question_type == 'short_answer':
                    question.correct_answer = request.form.get(f'test_correct_answer_{question_count}')
                
                question_count += 1
        
        # Add content creation activity
        activity = UserActivity(
            user_id=current_user.id,
            title='Content Created',
            description=f'You created new content: {title}'
        )
        db.session.add(activity)
        db.session.commit()
        
        flash('Content, course, and assessments created successfully!')
        return redirect(url_for('manage_content'))
    
    contents = Content.query.all()
    return render_template('admin/content.html', contents=contents)

@app.route('/admin/courses/create', methods=['GET', 'POST'])
@login_required
def admin_create_course():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('index'))

    if request.method == 'POST':
        # Get form data
        title = request.form.get('title')
        description = request.form.get('description')
        category_id = request.form.get('category_id')
        difficulty_level = request.form.get('difficulty_level')
        estimated_duration = float(request.form.get('estimated_duration', 0))
        prerequisites = request.form.getlist('prerequisites')
        tags = request.form.getlist('tags')
        
        # Handle image upload
        image = request.files.get('image')
        image_url = None
        if image and allowed_file(image.filename, 'image'):
            filename = secure_filename(image.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'images', filename)
            image.save(filepath)
            image_url = f'/static/uploads/images/{filename}'

        # Create course
        course = Course(
            title=title,
            description=description,
            category_id=category_id,
            difficulty_level=difficulty_level,
            estimated_duration=estimated_duration,
            image_url=image_url,
            is_published=True
        )

        # Add prerequisites
        if prerequisites:
            course.prerequisites = json.dumps(prerequisites)

        # Add tags
        if tags:
            for tag_name in tags:
                tag = Tag.query.filter_by(name=tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    db.session.add(tag)
                course.tags.append(tag)

        db.session.add(course)
        db.session.commit()

        # Add activity
        activity = UserActivity(
            user_id=current_user.id,
            title='Course Created',
            description=f'You created a new course: {course.title}'
        )
        db.session.add(activity)
        db.session.commit()

        flash('Course created successfully!')
        return redirect(url_for('course_detail', course_id=course.id))

    # GET request - show form
    categories = Category.query.all()
    existing_courses = Course.query.all()  # For prerequisites
    existing_tags = Tag.query.all()
    return render_template(
        'admin/create_course.html',
        categories=categories,
        existing_courses=existing_courses,
        existing_tags=existing_tags
    )

@app.route('/course/<int:course_id>/review', methods=['POST'])
@login_required
def add_review(course_id):
    course = Course.query.get_or_404(course_id)
    rating = request.form.get('rating', type=int)
    comment = request.form.get('comment')
    
    if not 1 <= rating <= 5:
        flash('Invalid rating')
        return redirect(url_for('course_detail', course_id=course_id))
    
    existing_review = Review.query.filter_by(
        user_id=current_user.id,
        course_id=course_id
    ).first()
    
    if existing_review:
        existing_review.rating = rating
        existing_review.comment = comment
        existing_review.updated_at = datetime.now(UTC)
    else:
        review = Review(
            user_id=current_user.id,
            course_id=course_id,
            rating=rating,
            comment=comment
        )
        db.session.add(review)
    
    # Add review activity
    activity = UserActivity(
        user_id=current_user.id,
        title='Course Review',
        description=f'You reviewed {course.title}'
    )
    db.session.add(activity)
    db.session.commit()
    
    flash('Review submitted successfully!')
    return redirect(url_for('course_detail', course_id=course_id))

@app.route('/course/<int:course_id>/progress', methods=['POST'])
@login_required
def update_progress(course_id):
    enrollment = Enrollment.query.filter_by(
        user_id=current_user.id,
        course_id=course_id
    ).first_or_404()
    
    section_id = request.form.get('section_id', type=int)
    completed = request.form.get('completed', type=bool)
    
    completed_sections = enrollment.completed_section_list
    if completed and section_id not in completed_sections:
        completed_sections.append(section_id)
    elif not completed and section_id in completed_sections:
        completed_sections.remove(section_id)
    
    enrollment.completed_sections = json.dumps(completed_sections)
    enrollment.progress = (len(completed_sections) / 
                         ContentSection.query.filter_by(content_id=course_id).count()) * 100
    enrollment.last_accessed = datetime.now(UTC)
    
    # Add progress activity if completed
    if enrollment.progress >= 100:
        activity = UserActivity(
            user_id=current_user.id,
            title='Course Completed',
            description=f'You completed {enrollment.course.title}'
        )
        db.session.add(activity)
    
    db.session.commit()
    return jsonify({'success': True, 'progress': enrollment.progress})

@app.route('/admin/categories', methods=['GET', 'POST'])
@login_required
def manage_categories():
    if not current_user.is_admin:
        flash('Access denied')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        if name:
            category = Category(name=name)
            db.session.add(category)
            db.session.commit()
            
            # Add category creation activity
            activity = UserActivity(
                user_id=current_user.id,
                title='Category Created',
                description=f'You created a new category: {name}'
            )
            db.session.add(activity)
            db.session.commit()
            
            flash('Category added successfully!')
    
    categories = Category.query.all()
    return render_template('admin/categories.html', categories=categories)

@app.route('/admin/tags', methods=['GET', 'POST'])
@login_required
def manage_tags():
    if not current_user.is_admin:
        flash('Access denied')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        if name:
            tag = Tag(name=name)
            db.session.add(tag)
            db.session.commit()
            
            # Add tag creation activity
            activity = UserActivity(
                user_id=current_user.id,
                title='Tag Created',
                description=f'You created a new tag: {name}'
            )
            db.session.add(activity)
            db.session.commit()
            
            flash('Tag added successfully!')
    
    tags = Tag.query.all()
    return render_template('admin/tags.html', tags=tags)

@app.route('/course/<int:course_id>/content/<int:section_id>')
@login_required
def view_section(course_id, section_id):
    course = Course.query.get_or_404(course_id)
    section = ContentSection.query.get_or_404(section_id)
    enrollment = Enrollment.query.filter_by(
        user_id=current_user.id,
        course_id=course_id
    ).first_or_404()
    
    # Update last accessed time
    enrollment.last_accessed = datetime.now(UTC)
    db.session.commit()
    
    return render_template('course_section.html',
                         course=course,
                         section=section,
                         enrollment=enrollment)

# Add new models for tests and PDF resources
class Test(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    passing_score = db.Column(db.Integer, default=70)  # Percentage
    time_limit = db.Column(db.Integer, default=0)  # Minutes, 0 = no limit
    created_at = db.Column(db.DateTime, default=datetime.now(UTC))
    
    # Relationships
    course = db.relationship('Course', backref=db.backref('tests', lazy=True))
    questions = db.relationship('Question', backref='test', lazy=True, cascade="all, delete-orphan")
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'passing_score': self.passing_score,
            'time_limit': self.time_limit,
            'questions_count': len(self.questions)
        }


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(20), nullable=False)  # multiple_choice, true_false, short_answer
    correct_option = db.Column(db.Integer)  # For multiple choice and true/false
    correct_answer = db.Column(db.String(255))  # For short answer
    
    # Relationship
    options = db.relationship('Option', backref='question', lazy=True, cascade="all, delete-orphan")
    
    def to_dict(self):
        return {
            'id': self.id,
            'text': self.text,
            'type': self.type,
            'options': [option.to_dict() for option in self.options],
            'correct_option': self.correct_option if self.type != 'short_answer' else None,
            'correct_answer': self.correct_answer if self.type == 'short_answer' else None
        }


class Option(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    text = db.Column(db.String(255), nullable=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'text': self.text
        }


class TestAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'), nullable=False)
    score = db.Column(db.Integer, default=0)
    completed = db.Column(db.Boolean, default=False)
    started_at = db.Column(db.DateTime, default=datetime.now(UTC))
    completed_at = db.Column(db.DateTime)
    passed = db.Column(db.Boolean, default=False)
    duration = db.Column(db.Integer)  # Duration in seconds
    timestamp = db.Column(db.DateTime, default=datetime.now(UTC))
    user = db.relationship('User', back_populates='test_attempts')
    test = db.relationship('Test')
    answers = db.relationship('TestAnswer', back_populates='test_attempt', cascade='all, delete-orphan')
    
    def calculate_duration(self):
        """Safely calculate duration between started_at and completed_at"""
        if not self.started_at or not self.completed_at:
            return None
        
        # Ensure both are timezone-aware for comparison
        if self.started_at.tzinfo is None:
            start_time = self.started_at.replace(tzinfo=UTC)
        else:
            start_time = self.started_at
            
        if self.completed_at.tzinfo is None:
            end_time = self.completed_at.replace(tzinfo=UTC)
        else:
            end_time = self.completed_at
            
        return int((end_time - start_time).total_seconds())


class TestAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_attempt_id = db.Column(db.Integer, db.ForeignKey('test_attempt.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    selected_option = db.Column(db.String(1))
    is_correct = db.Column(db.Boolean, default=False)
    test_attempt = db.relationship('TestAttempt', back_populates='answers')
    question = db.relationship('Question')


class PDFResource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    file_path = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(UTC))
    
    # Relationship
    course = db.relationship('Course', backref=db.backref('pdf_resources', lazy=True))
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'file_path': self.file_path,
            'created_at': self.created_at
        }

# Configure upload folder
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static/uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

# Create upload directories if they don't exist
os.makedirs(os.path.join(UPLOAD_FOLDER, 'images'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'pdfs'), exist_ok=True)

def allowed_file(filename, resource_type):
    ALLOWED_EXTENSIONS = {
        'pdf': {'pdf'},
        'video': {'mp4', 'webm'}
    }
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS.get(resource_type, set())

# Route for viewing course tests
@app.route('/course/<int:course_id>/tests')
@login_required
def course_tests(course_id):
    course = Course.query.get_or_404(course_id)
    tests = Test.query.filter_by(course_id=course_id).all()
    
    # Check if user is enrolled
    enrollment = None
    if current_user.is_authenticated:
        enrollment = Enrollment.query.filter_by(
            user_id=current_user.id,
            course_id=course_id
        ).first()
    
    # Get test attempts for this user
    test_attempts = {}
    if enrollment:
        attempts = TestAttempt.query.filter_by(user_id=current_user.id).filter(
            TestAttempt.test_id.in_([t.id for t in tests])
        ).all()
        
        for attempt in attempts:
            if attempt.test_id not in test_attempts or attempt.score > test_attempts[attempt.test_id]['score']:
                test_attempts[attempt.test_id] = {
                    'score': attempt.score,
                    'passed': attempt.passed,
                    'date': attempt.completed_at
                }
    
    return render_template('course_tests.html', course=course, tests=tests, 
                          enrollment=enrollment, test_attempts=test_attempts)

# Route for taking a test
@app.route('/test/<int:test_id>/take', methods=['GET', 'POST'])
@login_required
def take_test(test_id):
    test = db.session.get(Test, test_id)
    if not test:
        flash('Test not found', 'error')
        return redirect(url_for('dashboard'))
        
    course = test.course
    
    # Check if user is enrolled
    enrollment = Enrollment.query.filter_by(
        user_id=current_user.id,
        course_id=course.id
    ).first()
    
    if not enrollment and not current_user.is_admin:
        flash('You must be enrolled in this course to take tests.', 'error')
        return redirect(url_for('course_detail', course_id=course.id))
    
    # Check if user has any in-progress attempts
    in_progress = TestAttempt.query.filter_by(
        user_id=current_user.id,
        test_id=test_id,
        completed_at=None
    ).first()
    
    if request.method == 'POST':
        # Process test submission
        attempt_id = request.form.get('attempt_id')
        attempt = db.session.get(TestAttempt, attempt_id)
        
        if not attempt or attempt.user_id != current_user.id:
            flash('Invalid attempt.', 'error')
            return redirect(url_for('course_tests', course_id=course.id))
        
        # Check if test is already completed
        if attempt.completed_at:
            flash('This test has already been completed.', 'error')
            return redirect(url_for('test_results', attempt_id=attempt.id))
        
        # Process answers
        correct_answers = 0
        questions = Question.query.filter_by(test_id=test.id).all()
        
        for question in questions:
            answer_key = f'question_{question.id}'
            
            if question.type == 'multiple_choice' or question.type == 'true_false':
                selected_option = request.form.get(answer_key)
                if selected_option:
                    is_correct = int(selected_option) == question.correct_option
                    answer = TestAnswer(
                        test_attempt_id=attempt.id,
                        question_id=question.id,
                        selected_option=selected_option,
                        is_correct=is_correct
                    )
                    db.session.add(answer)
                    if is_correct:
                        correct_answers += 1
            
            elif question.type == 'short_answer':
                text_answer = request.form.get(answer_key)
                if text_answer:
                    # Simple exact match for short answer
                    is_correct = text_answer.strip().lower() == question.correct_answer.strip().lower()
                    answer = TestAnswer(
                        test_attempt_id=attempt.id,
                        question_id=question.id,
                        selected_option=text_answer,
                        is_correct=is_correct
                    )
                    db.session.add(answer)
                    if is_correct:
                        correct_answers += 1
        
        # Calculate score
        total_questions = len(questions)
        score = (correct_answers / total_questions) * 100 if total_questions > 0 else 0
        passed = score >= test.passing_score
        
        # Update attempt
        attempt.score = score
        attempt.passed = passed
        attempt.completed_at = datetime.now(UTC)
        
        # Calculate duration using the safe method
        attempt.duration = attempt.calculate_duration()
        
        db.session.commit()
        
        # Record activity
        activity = UserActivity(
            user_id=current_user.id,
            title=f"Completed Test: {test.title}",
            description=f"Scored {score:.1f}% on the test for {course.title}",
            activity_type="test_completion"
        )
        db.session.add(activity)
        
        # Update course progress if test is passed and user is enrolled
        if passed and enrollment:
            update_course_progress(enrollment.id)
        
        db.session.commit()
        
        flash(f'Test completed. Your score: {score:.1f}%', 'success')
        return redirect(url_for('test_results', attempt_id=attempt.id))
    
    # Start a new attempt if none in progress
    if not in_progress:
        attempt = TestAttempt(
            user_id=current_user.id,
            test_id=test_id,
            score=0,
            started_at=datetime.now(UTC)  # Ensure timezone-aware datetime
        )
        db.session.add(attempt)
        db.session.commit()
        in_progress = attempt
    
    # Get all questions for the test
    questions = Question.query.filter_by(test_id=test_id).all()
    
    return render_template('take_test.html', test=test, course=course, 
                          questions=questions, attempt=in_progress)

# Route for viewing test results
@app.route('/test/results/<int:attempt_id>')
@login_required
def test_results(attempt_id):
    attempt = db.session.get(TestAttempt, attempt_id)
    if not attempt:
        flash('Test attempt not found', 'error')
        return redirect(url_for('dashboard'))
    
    # Check if user owns this attempt
    if attempt.user_id != current_user.id and not current_user.is_admin:
        flash('You do not have permission to view these results.', 'error')
        return redirect(url_for('dashboard'))
    
    test = attempt.test
    course = test.course
    
    # Get all questions and answers
    questions = Question.query.filter_by(test_id=test.id).all()
    answers = TestAnswer.query.filter_by(test_attempt_id=attempt.id).all()
    
    # Map answers to questions for easy lookup
    answer_map = {a.question_id: a for a in answers}
    
    return render_template('test_results.html', attempt=attempt, test=test, 
                          course=course, questions=questions, answer_map=answer_map)

# Route for downloading PDF resources
@app.route('/course/<int:course_id>/pdf/<int:pdf_id>')
@login_required
def view_pdf(course_id, pdf_id):
    course = Course.query.get_or_404(course_id)
    pdf = PDFResource.query.get_or_404(pdf_id)
    
    # Check if PDF belongs to this course
    if pdf.course_id != course_id:
        flash('PDF not found for this course.', 'error')
        return redirect(url_for('course_detail', course_id=course_id))
    
    # Check if user is enrolled or admin
    if not current_user.is_admin:
        enrollment = Enrollment.query.filter_by(
            user_id=current_user.id,
            course_id=course_id
        ).first()
        
        if not enrollment:
            flash('You must be enrolled in this course to access resources.', 'error')
            return redirect(url_for('course_detail', course_id=course_id))
    
    # Record activity
    activity = UserActivity(
        user_id=current_user.id,
        title="Accessed PDF Resource",
        description=f"Viewed {pdf.title} from {course.title}",
        activity_type="resource_access"
    )
    db.session.add(activity)
    db.session.commit()
    
    # Render PDF viewer page
    return render_template('view_pdf.html', course=course, pdf=pdf)

# Helper function to update course progress
def update_course_progress(enrollment_id):
    enrollment = db.session.get(Enrollment, enrollment_id)
    if not enrollment:
        return
    
    course = db.session.get(Course, enrollment.course_id)
    # Check if sections exist
    sections_count = ContentSection.query.filter_by(content_id=course.content_id).count() if course.content_id else 0
    
    # Get completed sections
    completed_sections = len(enrollment.completed_section_list) if enrollment.completed_sections else 0
    
    # Check for tests
    tests = Test.query.filter_by(course_id=course.id).all()
    passed_tests = 0
    
    for test in tests:
        attempt = TestAttempt.query.filter_by(
            user_id=enrollment.user_id,
            test_id=test.id,
            passed=True
        ).first()
        
        if attempt:
            passed_tests += 1
    
    # Calculate progress including both sections and tests
    total_items = sections_count + len(tests)
    completed_items = completed_sections + passed_tests
    
    if total_items > 0:
        progress = (completed_items / total_items) * 100
    else:
        progress = 0
        
    enrollment.progress = progress
    
    if progress >= 100:
        enrollment.completion_date = datetime.now(UTC)
        
        # Record activity
        activity = UserActivity(
            user_id=enrollment.user_id,
            title="Course Completed",
            description=f"Completed the course: {course.title}",
            activity_type="course_completion"
        )
        db.session.add(activity)
    
    db.session.commit()

# Add a model for activities
class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    activity_type = db.Column(db.String(50))  # For easy filtering
    timestamp = db.Column(db.DateTime, default=datetime.now(UTC))
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'timestamp': self.timestamp
        }

# Section model for course content
class Section(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'))
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text)
    order = db.Column(db.Integer, nullable=False)
    video_url = db.Column(db.String(255))
    external_url = db.Column(db.String(255))
    
    # Relationship
    course = db.relationship('Course', backref=db.backref('sections', lazy=True, order_by='Section.order'))
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'order': self.order,
            'video_url': self.video_url,
            'external_url': self.external_url
        }

# Section completion tracking
class SectionCompletion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    enrollment_id = db.Column(db.Integer, db.ForeignKey('enrollment.id'))
    section_id = db.Column(db.Integer, db.ForeignKey('section.id'))
    completed_at = db.Column(db.DateTime, default=datetime.now(UTC))
    
    # Relationships
    enrollment = db.relationship('Enrollment', backref=db.backref('completions', lazy=True))
    section = db.relationship('Section')
    
    def to_dict(self):
        return {
            'section_id': self.section_id,
            'completed_at': self.completed_at
        }

@app.route('/course_catalog')
def course_catalog():
    # Get query parameters for filtering
    category_id = request.args.get('category', type=int)
    difficulty = request.args.get('difficulty')
    search = request.args.get('search', '')
    
    # Base query
    query = Course.query
    
    # Apply filters
    if category_id:
        query = query.filter(Course.category_id == category_id)
    
    if difficulty:
        query = query.filter(Course.difficulty_level == difficulty)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                Course.title.ilike(search_term),
                Course.description.ilike(search_term)
            )
        )
    
    # Only show published courses
    query = query.filter(Course.is_published == True)
    
    # Get courses with pagination
    page = request.args.get('page', 1, type=int)
    courses = query.order_by(Course.created_at.desc()).paginate(page=page, per_page=12)
    
    # Get categories for filter sidebar
    categories = Category.query.all()
    difficulty_levels = ['Beginner', 'Intermediate', 'Advanced']
    
    return render_template(
        'course_catalog.html',
        courses=courses,
        categories=categories,
        difficulty_levels=difficulty_levels,
        current_category=category_id,
        current_difficulty=difficulty,
        search_term=search
    )

class Quiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    time_limit = db.Column(db.Integer, default=0)  # Minutes, 0 = no limit
    passing_score = db.Column(db.Integer, default=70)  # Percentage
    created_at = db.Column(db.DateTime, default=datetime.now(UTC))
    
    # Relationships
    course = db.relationship('Course', backref=db.backref('quizzes', lazy=True))
    questions = db.relationship('QuizQuestion', backref='parent_quiz', lazy=True, cascade="all, delete-orphan")
    quiz_attempts = db.relationship('QuizAttempt', backref='parent_quiz', lazy=True)

class QuizQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20), nullable=False)  # multiple_choice, true_false
    points = db.Column(db.Integer, default=1)
    
    # Relationships
    options = db.relationship('QuizOption', backref='question', lazy=True, 
                            cascade="all, delete-orphan",
                            foreign_keys='QuizOption.question_id')

class QuizOption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('quiz_question.id'), nullable=False)
    option_text = db.Column(db.String(255), nullable=False)
    is_correct = db.Column(db.Boolean, default=False)

class QuizAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_attempt_id = db.Column(db.Integer, db.ForeignKey('quiz_attempt.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('quiz_question.id'), nullable=False)
    selected_option_id = db.Column(db.Integer, db.ForeignKey('quiz_option.id'))
    is_correct = db.Column(db.Boolean, default=False)
    
    # Relationships
    quiz_attempt = db.relationship('QuizAttempt', back_populates='answers')
    question = db.relationship('QuizQuestion')
    selected_option = db.relationship('QuizOption')

class QuizAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    score = db.Column(db.Float)
    started_at = db.Column(db.DateTime, default=datetime.now(UTC))
    completed_at = db.Column(db.DateTime)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('quiz_attempts', lazy=True))
    answers = db.relationship('QuizAnswer', back_populates='quiz_attempt', lazy=True, cascade="all, delete-orphan")

class StudyResource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    resource_type = db.Column(db.String(20), nullable=False)  # pdf, video
    file_path = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now(UTC))
    
    # Relationships
    course = db.relationship('Course', backref=db.backref('study_resources', lazy=True))
    views = db.relationship('ResourceView', backref='resource', lazy=True)

class ResourceView(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    resource_id = db.Column(db.Integer, db.ForeignKey('study_resource.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    viewed_at = db.Column(db.DateTime, default=datetime.now(UTC))

@app.route('/course/<int:course_id>/quiz/create', methods=['GET', 'POST'])
@login_required
def create_quiz(course_id):
    if not current_user.is_admin:
        flash('Access denied')
        return redirect(url_for('course_detail', course_id=course_id))
    
    course = Course.query.get_or_404(course_id)
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        time_limit = request.form.get('time_limit', type=int)
        passing_score = request.form.get('passing_score', type=int)
        
        quiz = Quiz(
            course_id=course_id,
            title=title,
            description=description,
            time_limit=time_limit,
            passing_score=passing_score
        )
        db.session.add(quiz)
        db.session.commit()
        
        # Add questions
        question_count = int(request.form.get('question_count', 0))
        for i in range(question_count):
            question_text = request.form.get(f'question_{i}')
            question_type = request.form.get(f'question_type_{i}')
            points = request.form.get(f'points_{i}', type=int, default=1)
            
            question = QuizQuestion(
                quiz_id=quiz.id,
                question_text=question_text,
                question_type=question_type,
                points=points
            )
            db.session.add(question)
            db.session.flush()  # Get question ID
            
            # Add options
            option_count = int(request.form.get(f'option_count_{i}', 0))
            for j in range(option_count):
                option_text = request.form.get(f'option_{i}_{j}')
                is_correct = request.form.get(f'correct_{i}_{j}') == 'on'
                
                option = QuizOption(
                    question_id=question.id,
                    option_text=option_text,
                    is_correct=is_correct
                )
                db.session.add(option)
                db.session.flush()
                
                if is_correct:
                    question.correct_option_id = option.id
        
        db.session.commit()
        flash('Quiz created successfully!')
        return redirect(url_for('course_detail', course_id=course_id))
    
    return render_template('create_quiz.html', course=course)

@app.route('/course/<int:course_id>/quiz/<int:quiz_id>/take', methods=['GET', 'POST'])
@login_required
def take_quiz(course_id, quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)
    course = Course.query.get_or_404(course_id)
    
    # Check if user is enrolled
    enrollment = Enrollment.query.filter_by(
        user_id=current_user.id,
        course_id=course_id
    ).first()
    
    if not enrollment and not current_user.is_admin:
        flash('You must be enrolled in this course to take quizzes.', 'error')
        return redirect(url_for('course_detail', course_id=course_id))
    
    if request.method == 'POST':
        attempt = QuizAttempt(
            quiz_id=quiz_id,
            user_id=current_user.id,
            started_at=datetime.now(UTC)  # Make sure started_at is timezone-aware
        )
        db.session.add(attempt)
        db.session.flush()
        
        score = 0
        total_points = 0
        
        for question in quiz.questions:
            total_points += question.points
            answer_key = f'question_{question.id}'
            selected_option_id = request.form.get(answer_key, type=int)
            
            if selected_option_id:
                selected_option = QuizOption.query.get(selected_option_id)
                is_correct = selected_option and selected_option.is_correct
                
                answer = QuizAnswer(
                    quiz_attempt_id=attempt.id,
                    question_id=question.id,
                    selected_option_id=selected_option_id,
                    is_correct=is_correct
                )
                db.session.add(answer)
                
                if is_correct:
                    score += question.points
        
        attempt.score = (score / total_points) * 100 if total_points > 0 else 0
        attempt.completed_at = datetime.now(UTC)  # Make sure completed_at is timezone-aware
        db.session.commit()
        
        flash(f'Quiz completed. Your score: {attempt.score:.1f}%')
        return redirect(url_for('quiz_results', attempt_id=attempt.id))
    
    return render_template('take_quiz.html', quiz=quiz, course=course)

@app.route('/course/<int:course_id>/resource/upload', methods=['GET', 'POST'])
@login_required
def upload_resource(course_id):
    if not current_user.is_admin:
        flash('Access denied')
        return redirect(url_for('course_detail', course_id=course_id))
    
    course = Course.query.get_or_404(course_id)
    
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        resource_type = request.form.get('resource_type')
        
        if 'file' not in request.files:
            flash('No file uploaded')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected')
            return redirect(request.url)
        
        if file and allowed_file(file.filename, resource_type):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            unique_filename = f"{timestamp}_{filename}"
            
            # Save file based on resource type
            if resource_type == 'pdf':
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'pdfs', unique_filename)
            else:  # video
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'videos', unique_filename)
            
            file.save(file_path)
            
            resource = StudyResource(
                course_id=course_id,
                title=title,
                description=description,
                resource_type=resource_type,
                file_path=f"/static/uploads/{resource_type}s/{unique_filename}"
            )
            db.session.add(resource)
            db.session.commit()
            
            flash('Resource uploaded successfully!')
            return redirect(url_for('course_detail', course_id=course_id))
        
        flash('Invalid file type')
        return redirect(request.url)
    
    return render_template('upload_resource.html', course=course)

@app.route('/course/<int:course_id>/resource/<int:resource_id>')
@login_required
def view_resource(course_id, resource_id):
    course = Course.query.get_or_404(course_id)
    resource = StudyResource.query.get_or_404(resource_id)
    
    # Check if user is enrolled
    enrollment = Enrollment.query.filter_by(
        user_id=current_user.id,
        course_id=course_id
    ).first()
    
    if not enrollment and not current_user.is_admin:
        flash('You must be enrolled in this course to access resources.', 'error')
        return redirect(url_for('course_detail', course_id=course_id))
    
    # Record view
    view = ResourceView(
        resource_id=resource_id,
        user_id=current_user.id
    )
    db.session.add(view)
    db.session.commit()
    
    return render_template('view_resource.html', course=course, resource=resource)

@app.route('/admin/content/<int:content_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_content(content_id):
    if not current_user.is_admin:
        flash('Access denied')
        return redirect(url_for('index'))
    
    content = Content.query.get_or_404(content_id)
    
    if request.method == 'POST':
        content.title = request.form.get('title')
        content.content = request.form.get('content')
        db.session.commit()
        
        # Add content edit activity
        activity = UserActivity(
            user_id=current_user.id,
            title='Content Edited',
            description=f'You edited content: {content.title}'
        )
        db.session.add(activity)
        db.session.commit()
        
        flash('Content updated successfully!')
        return redirect(url_for('manage_content'))
    
    return render_template('admin/edit_content.html', content=content)

@app.route('/admin/content/<int:content_id>/delete')
@login_required
def delete_content(content_id):
    if not current_user.is_admin:
        flash('Access denied')
        return redirect(url_for('index'))
    
    content = Content.query.get_or_404(content_id)
    
    # Add content deletion activity
    activity = UserActivity(
        user_id=current_user.id,
        title='Content Deleted',
        description=f'You deleted content: {content.title}'
    )
    db.session.add(activity)
    
    # Delete associated course if exists
    course = Course.query.filter_by(content_id=content_id).first()
    if course:
        # Delete quizzes associated with the course first
        quizzes = Quiz.query.filter_by(course_id=course.id).all()
        for quiz in quizzes:
            db.session.delete(quiz)
        
        # Delete tests associated with the course
        tests = Test.query.filter_by(course_id=course.id).all()
        for test in tests:
            db.session.delete(test)
        
        db.session.flush()  # Commit the quiz and test deletions first
        db.session.delete(course)
    
    db.session.delete(content)
    db.session.commit()
    
    flash('Content deleted successfully!')
    return redirect(url_for('manage_content'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Create admin user if it doesn't exist
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin_user = User(
                username='admin',
                email='admin@example.com',
                password_hash=generate_password_hash('admin123'),
                is_admin=True,
                created_at=datetime.now(UTC)
            )
            db.session.add(admin_user)
            db.session.commit()
            print("Admin user created")
        
        # Create default categories if they don't exist
        if Category.query.count() == 0:
            categories = [
                "Programming", "Data Science", "Web Development", 
                "Mobile Development", "DevOps", "Design"
            ]
            for cat_name in categories:
                category = Category(name=cat_name)
                db.session.add(category)
            db.session.commit()
            print("Default categories created")
    
    app.run(debug=True, port=5006) 