import re

def validate_email(email):
    """Validate the format of an email address.\n    \n    Args:
        email (str): The email address to validate.\n    \n    Returns:
        bool: True if the email is valid, False otherwise.\n    """
    if not isinstance(email, str):
        return False
    pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return re.match(pattern, email) is not None