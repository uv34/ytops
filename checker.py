import re

def check_username(username):
    """
    Check if the username is valid.
    :param username: The username to check.
    :return: True if the username is valid, False otherwise.
    """
    # Check if the username is empty
    if not username:
        return False

    # Check if the username is too long
    if len(username) < 6 or len(username) > 20:
        return False

    # Check if the username contains invalid characters
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False

    return True


def check_password(password):
    """
    Check if the password is valid.
    :param password: The password to check.
    :return: True if the password is valid, False otherwise.
    """
    # Check if the password is empty
    if not password:
        return False

    # Check if the password is too short
    if len(password) < 6 or len(password) > 20:
        return False

    # Check if the password contains invalid characters
    if not re.match(r'^[a-zA-Z0-9_!@#$%^&*]+$', password):
        return False

    return True


def check_email(email):
    """
    Check if the email is valid.
    :param email: The email to check.
    :return: True if the email is valid, False otherwise.
    """
    # Check if the email is empty
    if not email:
        return False

    # Check if the email is too long
    if len(email) > 50:
        return False

    # Check if the email contains invalid characters
    if not re.match(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$', email):
        return False

    return True

if __name__ == '__main__':
    print(check_email('uvlevy100@gmail.com'))
    print(check_email('sdasda@kdror.co.il'))
    print(check_email('sdasda@kdror'))
    print(check_email('sdasda@kdror.c'))
    print(check_email('sdasda@kdror.co.il.co'))
