class Config:
    HOST = "localhost"
    USER = "root"
    PASSWORD = "system"
    DATABASE = "internship"

    # Session secret for Flask login (change this for production)
    SECRET_KEY = "change-me"

    # Demo credentials (minimal auth without creating user tables)
    ADMIN_USERNAME = "admin"
    ADMIN_PASSWORD = "admin123"

    DEPARTMENT_USERNAME = "department"
    DEPARTMENT_PASSWORD = "dept123"

    OFFICE_USERNAME = "office"
    OFFICE_PASSWORD = "office123"

    # Student login: any Register Number + this password
    STUDENT_PASSWORD = "student123"