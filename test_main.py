import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from main import app, connect_db


@pytest.fixture
def test_client():
    return TestClient(app)

@pytest.fixture
def mock_db_connection():
    with patch('main.psycopg2.connect') as mock_connect:
        mock_connection = MagicMock()
        mock_cursor = MagicMock()

        mock_cursor.__enter__.return_value = mock_cursor

        mock_connect.return_value = mock_connection

        yield mock_connection, mock_cursor 
        
@pytest.fixture(autouse=True)
def reset_mocks(mock_db_connection):
    mock_connection, mock_cursor = mock_db_connection
    mock_connection.reset_mock()
    
    # Reset the mock_cursor as well
    mock_cursor.reset_mock()
    yield

def test_connect_db_success(mock_db_connection):
    mock_connection, mock_cursor = mock_db_connection
    mock_connection.cursor.return_value = mock_cursor

    result = connect_db()

    assert result is True

def test_health(test_client):

    response = test_client.get("/health/")
    assert response.status_code == 200
    assert response.json()['detail'] == "Server is healthy"


@pytest.mark.parametrize("username, email, locality, first_name, last_name, description, expected_status_code, expected_message", [
    # Its a test for the use case used in our project
    # You can pass the locality, first_name, last_name, description (!= None) but for default it will be passed as None for that attributes 
    # You dont even need to pass them in formData, for default it will be passed as None if there is no value passed in formData
    ("TestUser", "testuser123@gmail.com", None, None, None, None, 200, "User Profile created successfully!"),
])
def test_create_profile_success(test_client, username, email, locality, first_name, last_name, description,expected_status_code, expected_message, mock_db_connection):
    mock_connection, mock_cursor = mock_db_connection

    form_data = {
        "username": username,
        "email": email,
        "locality": locality,
        "first_name": first_name,
        "last_name": last_name,
        "description": description
    }
    
    mock_cursor.fetchone.return_value = None  # Ensure that the user does not exist
    mock_connection.cursor.return_value = mock_cursor
    
    with patch('main.connection', mock_connection):
        response = test_client.post("/profile/", data=form_data)
    

    assert response.status_code == expected_status_code
    assert response.json()['message'] == expected_message


@pytest.mark.parametrize("username, email, locality, first_name, last_name, description, expected_status_code, expected_detail", [
    ("TestUser", "testuser@gmail.com", None, None, None, None, 400, "User already exists"),
])
def test_create_profile_failure(test_client, username, email, locality, first_name, last_name, description,expected_status_code, expected_detail):

    form_data = {
        "username": username,
        "email": email,
        "locality": locality,
        "first_name": first_name,
        "last_name": last_name,
        "description": description
    }

    response = test_client.post("/profile/", data=form_data)

    assert response.json()['status_code'] == expected_status_code
    assert response.json()['detail'] == expected_detail


@pytest.mark.parametrize("email, locality, first_name, last_name, description, interests, image, expected_status_code, expected_message", [
    
    ("testuser@gmail.com", 'Aveiro', "test", "user", "Animal's Lover", "Dogs,Cats", [('test_images/Profile.png', open('test_images/Profile.png', 'rb'))], 200, "User Profile updated successfully!"),
    ("testuser@gmail.com", 'Aveiro', "test", "user", "Animal's Lover", "Cats", [('test_images/Profile.png', open('test_images/Profile.png', 'rb'))], 200, "User Profile updated successfully!"),
    ("testuser@gmail.com", None, "test", "user", "Animal's Lover", "Dogs,Cats", [('test_images/Profile.png', open('test_images/Profile.png', 'rb'))], 200, "User Profile updated successfully!"),
    ("testuser@gmail.com", 'Aveiro', None, "user", "Animal's Lover", "Dogs,Cats", [('test_images/Profile.png', open('test_images/Profile.png', 'rb'))], 200, "User Profile updated successfully!"),
    ("testuser@gmail.com", 'Aveiro', "test", None, "Animal's Lover", "Dogs,Cats", [('test_images/Profile.png', open('test_images/Profile.png', 'rb'))], 200, "User Profile updated successfully!"),
    ("testuser@gmail.com", 'Aveiro', "test", "user", None, "Dogs,Cats", [('test_images/Profile.png', open('test_images/Profile.png', 'rb'))], 200, "User Profile updated successfully!"),
    ("testuser@gmail.com", 'Aveiro', "test", "user", "Animal's Lover", None, [('test_images/Profile.png', open('test_images/Profile.png', 'rb'))], 200, "User Profile updated successfully!"),
    ("testuser@gmail.com", 'Aveiro', "test", "user", "Animal's Lover", "Dogs,Cats", None, 200, "User Profile updated successfully!"),
    ("testuser@gmail.com", 'Aveiro', "test", "user", None, None, None, 200, "User Profile updated successfully!"),
    ("testuser@gmail.com", 'Aveiro', None, None, "Animal's Lover", "Dogs,Cats", None, 200, "User Profile updated successfully!"),
    ("testuser@gmail.com", None, None, None, None, None, None, 200, "User Profile updated successfully!"),
])
def test_edit_profile_success(test_client, email, locality, first_name, last_name, description, interests, image, expected_status_code, expected_message):

    form_data = {
        "locality": locality,
        "first_name": first_name,
        "last_name": last_name,
        "description": description,
        "interests": interests,
        
    }
    
    response = test_client.put(f"/profile/{email}", data=form_data, files=image)

    assert response.status_code == expected_status_code
    assert response.json()['message'] == expected_message


def test_edit_profile_user_not_found(test_client, mock_db_connection):
    
    mock_connection, mock_cursor = mock_db_connection
    mock_cursor.fetchone.return_value = None
    
    email = "nonexistent@gmail.com"

    form_data = {
        "locality": "Aveiro",
        "first_name": "test",
        "last_name": "user",
        "description": "Animal's Lover",
        "interests": "Dogs",
    }

    mock_connection.cursor.return_value = mock_cursor

    with patch('main.connection', mock_connection):
        response = test_client.put(f"/profile/{email}", data=form_data)
    
    assert response.json()['status_code'] == 404
    assert response.json()['detail'] == "User not found"    

    
def test_get_user_profile(test_client, mock_db_connection):
    
    mock_connection, mock_cursor = mock_db_connection

    email = "test@example.com"

    user_profile = {
        "user_id": str(uuid4()),
        "username": "test_user",
        "email": email,
        "locality": "Aveiro",
        "first_name": "John",
        "last_name": "Doe",
        "description": "User description",
        "interests": [
            {
                "interest": "Cat"
            }
        ],
        "image": []
    }

    mock_cursor.fetchone.return_value = tuple(user_profile.values())
    mock_cursor.fetchall.return_value = []
    mock_connection.cursor.return_value = mock_cursor

    with patch('main.connection', mock_connection):

        response = test_client.get(f"/profile/{email}")

    assert response.status_code == 200
    assert response.json() == {
        "user_id": user_profile["user_id"],
        "username": user_profile["username"],
        "email": user_profile["email"],
        "locality": user_profile["locality"],
        "first_name": user_profile["first_name"],
        "last_name": user_profile["last_name"],
        "description": user_profile["description"],
        "interests": user_profile["interests"],
        "image": user_profile["image"]
    }    
    
def test_get_user_profile_not_found(test_client, mock_db_connection):
    mock_connection, mock_cursor = mock_db_connection
    email = "nonexistent@gmail.com"

    mock_cursor.fetchone.return_value = None
    mock_cursor.fetchall.return_value = []
    mock_connection.cursor.return_value = mock_cursor

    with patch('main.connection', mock_connection):
        response = test_client.get(f"/profile/{email}")
        
    assert response.json()['status_code'] == 404
    assert response.json()['detail'] == "User not found"
    
    
def test_get_users_by_interest(test_client, mock_db_connection):
    mock_connection, mock_cursor = mock_db_connection

    interest = "Dogs"

    # Define mock data for users with the specified interest
    mock_data = [("user1@example.com",), ("user2@example.com",)]

    mock_cursor.fetchall.return_value = mock_data
    mock_connection.cursor.return_value = mock_cursor

    with patch('main.connection', mock_connection):
        response = test_client.get(f"/profile/users/{interest}")

    assert response.status_code == 200
    assert response.json() == ["user1@example.com", "user2@example.com"]
    

def test_get_users_by_interest_internal_server_error(test_client, mock_db_connection):
    mock_connection, mock_cursor = mock_db_connection

    interest = "Cat"

    # Configure mock cursor to raise an exception 
    mock_cursor.execute.side_effect = Exception("Simulated database error")
    mock_connection.cursor.return_value = mock_cursor

    with patch('main.connection', mock_connection):
        response = test_client.get(f"/profile/users/{interest}")
        
    print(response.status_code)
    print(response.json())

    assert response.json()['status_code'] == 500
    assert response.json()['detail'] == "Internal Server Error"