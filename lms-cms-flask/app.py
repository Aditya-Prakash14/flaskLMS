from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lms_cms.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database Models
class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500))
    content_id = db.Column(db.Integer, db.ForeignKey('content.id'))

class Content(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    body = db.Column(db.Text, nullable=False)

# Create database tables
with app.app_context():
    db.create_all()

# Routes
@app.route('/')
def home():
    return render_template('base.html')

# LMS Routes
@app.route('/courses')
def courses():
    all_courses = Course.query.all()
    return render_template('courses.html', courses=all_courses)

@app.route('/enroll/<int:course_id>')
def enroll(course_id):
    course = Course.query.get_or_404(course_id)
    # Simulate enrollment (could add user tracking here)
    return f"Enrolled in {course.title}"

# CMS Routes
@app.route('/content')
def content():
    all_content = Content.query.all()
    return render_template('content.html', contents=all_content)

@app.route('/add_content', methods=['GET', 'POST'])
def add_content():
    if request.method == 'POST':
        title = request.form['title']
        body = request.form['body']
        new_content = Content(title=title, body=body)
        db.session.add(new_content)
        db.session.commit()
        
        # Optionally create a course linked to this content
        new_course = Course(title=title, description="Auto-generated course", content_id=new_content.id)
        db.session.add(new_course)
        db.session.commit()
        return redirect(url_for('content'))
    return render_template('add_content.html')

if __name__ == '__main__':
    app.run(debug=True)