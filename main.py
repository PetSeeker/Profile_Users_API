import boto3, psycopg2, os, logging
from fastapi import FastAPI, Form, HTTPException, UploadFile, File, Query 
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from uuid import UUID, uuid4
import uuid
import json

# FastAPI App Configuration
app = FastAPI(debug=True)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

load_dotenv()

AWS_BUCKET = os.getenv("BUCKET")
ACCESS_KEY = os.getenv("ACCESS_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")
REGION = os.getenv("REGION")

s3 = boto3.resource('s3', aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY, region_name=REGION)
bucket = s3.Bucket(AWS_BUCKET)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_DATABASE = os.getenv("DB_DATABASE")

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    while not connect_db():
            continue

# Database Connection
def connect_db():
    global connection, cursor
    try:
        connection = psycopg2.connect(user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT, database=DB_DATABASE)

        cursor = connection.cursor()
        if connection:
            cursor.execute("SELECT version();")
            db_version = cursor.fetchone()
            logger.info(f"Connected to {db_version[0]}")
            create_tables()
            return True
        else:
            logger.error("Failed to connect to the database.")
            return False
    except (Exception, psycopg2.Error) as error:
        logger.error(f"Error while connecting to PostgreSQL: {error}")
        return False
    
    
@app.get("/health/")
async def health():
    return HTTPException(status_code=200, detail="Server is healthy")


#Create users profile
@app.post("/profile/")
async def create_user(
    username: str = Form(...),
    email: str = Form(...),
    locality: str = Form(None),
    first_name: str = Form(None),
    last_name: str = Form(None),
    description: str = Form(None),
    image: UploadFile = Form(None)
):
    global connection
    try:
        with connection.cursor() as cursor:
            
            check_query = "SELECT * FROM users_profile WHERE email = %s"
            cursor.execute(check_query, (email,))
            existing_user = cursor.fetchone()
            
            if existing_user:
                return HTTPException(status_code=400, detail="User already exists")
                 
            insert_user_profile_data(cursor,username,email,locality,first_name,last_name,description)
            
            connection.commit()

            return {"message": "User Profile created successfully!"}
    
    except Exception as e:
        connection.rollback()
        logger.error(f"Error adding listing: {e}")
        return HTTPException(status_code=500, detail="Internal Server Error")

#Edit user's profile
@app.put("/profile/{email}")
async def edit_user(
    email: str,
    locality: str = Form(None),
    first_name: str = Form(None),
    last_name: str = Form(None),
    description: str = Form(None),
    #interests: list[str] = Form(None),
    interests: str = Form(None),
    image: UploadFile = Form(None)
):
    
    global connection
    try:
        with connection.cursor() as cursor:
            
            check_query = "SELECT * FROM users_profile WHERE email = %s"
            cursor.execute(check_query, (email,))
            existing_user = cursor.fetchone()
            
            if not existing_user:
                return HTTPException(status_code=404, detail="User not found")
            
            # Convert comma-separated interests to an array of JSON objects
            interests_list = []
            if interests:
                for interest in interests.split(','):   
                    interests_list.append({"interest": interest.strip()})   
            
            update_query = """
                UPDATE users_profile 
                SET locality = %s,
                    first_name = %s,
                    last_name = %s,
                    description = %s,
                    interests = %s::jsonb
                WHERE email = %s
            """
            
            cursor.execute(
                update_query,
                (locality, first_name, last_name, description, json.dumps(interests_list), email),
            )
            
            if image:
                # Check if there are existing images for the user_id
                select_images_query = "SELECT * FROM images WHERE user_profile_id = %s"
                cursor.execute(select_images_query, (str(existing_user[0]),))
                existing_images = cursor.fetchall()
                
                if existing_images:
                    logger.info("Update existing image")
                    image_url = upload_image_to_s3(image)
                    update_image_data(cursor, image.filename, image_url, str(existing_user[0]))
                else:
                    logger.info(f"Inserting image: {image}")
                    image_url = upload_image_to_s3(image)
                    insert_image_data(cursor, image.filename, image_url, str(existing_user[0]))

            connection.commit()

            return {"message": "User Profile updated successfully!"}

    except Exception as e:
        connection.rollback()
        logger.error(f"Error updating user: {e}")
        return HTTPException(status_code=500, detail="Internal Server Error")
    
#Get user's profile given an email
@app.get("/profile/{email}")
async def get_user(email: str):
    global connection
    try:
        with connection.cursor() as cursor:
            select_query = "SELECT * FROM users_profile WHERE email = %s"
            cursor.execute(select_query, (email,))
            user = cursor.fetchone()

            if not user:
                return HTTPException(status_code=404, detail="User not found")
            
            image = get_images_for_users_profile(str(user[0]), cursor)

            user_info = {
                "user_id": user[0],
                "username": user[1],
                "email": user[2],
                "locality": user[3],
                "first_name": user[4],
                "last_name": user[5],
                "description": user[6],
                "interests": user[7],
                "image": image
            }

            return user_info

    except Exception as e:
        logger.error(f"Error retrieving user: {e}")
        return HTTPException(status_code=500, detail="Internal Server Error")

#Get user's with the given interest    
@app.get("/profile/users/{interest}")
async def get_interests(interest: str):
    global connection
    try:
        with connection.cursor() as cursor:
            select_query = "SELECT email FROM users_profile WHERE interests @> %s::jsonb"
            cursor.execute(select_query, (json.dumps([{"interest": interest}]),))
            emails_with_interest = cursor.fetchall()

            email_list = [user[0] for user in emails_with_interest]

            return email_list

    except Exception as e:
        logger.error(f"Error retrieving user emails by interest: {e}")
        return HTTPException(status_code=500, detail="Internal Server Error")
   
   
#Just for Debugging... 
@app.get("/profile/all/")
async def get_all_users():
    global connection
    try:
        with connection.cursor() as cursor:
            select_all_query = "SELECT * FROM users_profile"
            cursor.execute(select_all_query)
            all_users = cursor.fetchall()

            user_list = [
                {
                    "user_id": user[0],
                    "username": user[1],
                    "email": user[2],
                    "locality": user[3],
                    "first_name": user[4],
                    "last_name": user[5],
                    "description": user[6],
                    "interests": user[7],
                }
                for user in all_users
            ]

            return user_list

    except Exception as e:
        logger.error(f"Error retrieving all users: {e}")
        return HTTPException(status_code=500, detail="Internal Server Error")    


#Just for Debugging...
# @app.delete("/deleteGender/")
# async def remove_gender():
#     global connection
#     try:
#         with connection.cursor() as cursor:
#             remove_query = "ALTER TABLE users_profile DROP COLUMN IF EXISTS gender;"
#             cursor.execute(remove_query)
#             connection.commit()
#             return {"message": "Column 'gender' removed successfully from users_profile table"}
            
#     except Exception as e:
#         logger.error(f"Error retrieving all users: {e}")
#         return HTTPException(status_code=500, detail="Internal Server Error") 

def create_tables():
    try:
        global connection, cursor

        # Create the 'users' table
        create_users_table = """
            CREATE TABLE IF NOT EXISTS users_profile (
                user_id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                username VARCHAR NOT NULL,
                email VARCHAR NOT NULL UNIQUE,
                locality VARCHAR,
                first_name VARCHAR,
                last_name VARCHAR,
                description TEXT,
                interests JSONB
            );
        """

        cursor = connection.cursor()
        cursor.execute(create_users_table)
        
        create_images_table = """
            CREATE TABLE IF NOT EXISTS images (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                image_name TEXT NOT NULL,
                image_url TEXT NOT NULL,
                user_profile_id UUID REFERENCES users_profile(user_id) ON DELETE CASCADE
            );
        """
        cursor.execute(create_images_table)
        
        connection.commit()
        logger.info("Tables created successfully in PostgreSQL database")

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f"Error creating table: {error}")


def insert_user_profile_data(cursor, username, email, locality, first_name, last_name, description):
    insert_query = "INSERT INTO users_profile (username, email, locality, first_name, last_name, description, interests) VALUES (%s,%s, %s, %s, %s, %s, %s, %s::jsonb)"
    cursor.execute(insert_query, (username, email, locality, first_name, last_name, description, []))

def upload_image_to_s3(image):
    random_string = str(uuid4())
    unique_filename = f"{random_string}_{image.filename}"
    image_url = f"https://{AWS_BUCKET}.s3.amazonaws.com/{unique_filename}"
    bucket.upload_fileobj(image.file, unique_filename, ExtraArgs={"ACL": "public-read"})
    return image_url

def insert_image_data(cursor, image_filename, image_url, user_id):
    insert_query = "INSERT INTO images (image_name, image_url, user_profile_id) VALUES (%s, %s, %s)"
    cursor.execute(insert_query, (image_filename, image_url, user_id))
    
def update_image_data(cursor, image_filename, image_url, user_id):
    update_image_query = "UPDATE images SET image_name = %s, image_url = %s WHERE user_profile_id = %s"
    cursor.execute(update_image_query, (image_filename, image_url, user_id))
    
def get_images_for_users_profile(user_id, cursor):
    cursor.execute("SELECT image_url FROM images WHERE user_profile_id = %s", (user_id,))
    image_rows = cursor.fetchall()
    images = [image[0] for image in image_rows]
    return images
    
