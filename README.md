# Learning Management System

A Flask-based Learning Management System with course management, user authentication, and assessment features.

## Features

- User authentication and authorization
- Course management
- Test and quiz creation
- PDF resource management
- Progress tracking
- Admin dashboard

## Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd <repository-name>
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a .env file with the following variables:
```
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///lms.db
```

5. Initialize the database:
```bash
flask db init
flask db migrate
flask db upgrade
```

## Development

Run the development server:
```bash
flask run
```

## Deployment

### Heroku

1. Create a Heroku account and install the Heroku CLI
2. Login to Heroku:
```bash
heroku login
```

3. Create a new Heroku app:
```bash
heroku create <app-name>
```

4. Set environment variables:
```bash
heroku config:set FLASK_ENV=production
heroku config:set SECRET_KEY=your-secret-key-here
heroku config:set DATABASE_URL=your-database-url
```

5. Deploy to Heroku:
```bash
git push heroku main
```

6. Initialize the database:
```bash
heroku run flask db upgrade
```

### Other Platforms

For other platforms, ensure you:
1. Set the appropriate environment variables
2. Use a production-grade WSGI server (gunicorn)
3. Configure a production database
4. Set up proper static file serving
5. Configure SSL/TLS

## Security Considerations

- Always use strong, unique SECRET_KEY in production
- Use HTTPS in production
- Keep dependencies updated
- Regularly backup the database
- Monitor for security vulnerabilities

## License

MIT License 