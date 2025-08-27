import os
import requests

def upload_file_to_gcs(object_location, session_uri):
    """
    Uploads a file to Google Cloud Storage using a resumable session URI.

    Args:
        object_location (str): The path to the local file to be uploaded.
        session_uri (str): The session URI for the resumable upload.
    """
    # Get the size of the file for the 'Content-Length' header
    headers = {
        'Content-Length': str(os.path.getsize(object_location))
    }

    try:
        with open(object_location, 'rb') as f:
            response = requests.put(session_uri, data=f, headers=headers)
        
        # Print the response status
        if response.status_code in (200, 201):
            print("Upload successful!")
        elif response.status_code in (308, 500, 503):
            print("Upload Incomplete, please continue uploading the data")
            resume_upload(session_uri, object_location, response)
        else:
            print(f"Failed to upload: {response.status_code}")
            print(response.text)
        
    except FileNotFoundError:
        print(f"Error: The file '{object_location}' was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")


def check_upload_status(session_uri):
    """
    Checks the status of a resumable upload in Google Cloud Storage.

    Args:
        session_uri (str): The session URI for the resumable upload.

    Returns:
        dict: Information about the upload status or an error message.
    """
    headers = {
        'Content-Length': '0',
        'Content-Range': 'bytes */*'  # Using */* to indicate an unknown object size
    }

    response = requests.put(session_uri, headers=headers)

    # Process the response
    if response.status_code == 308:
        print("Upload is incomplete.")
        return {
            "status": "incomplete",
            "range": response.headers.get('Range', 'Not provided')
        }
    elif response.status_code == 200 or response.status_code == 201:
        print("Upload is complete!")
        return {
            "status": "complete"
        }
    else:
        print(f"Error checking upload status: {response.status_code}")
        return {
            "status": "error",
            "details": response.text
        }


def resume_upload(session_uri, object_location, status_response):
    """
    Resumes an interrupted upload using the Range header from the status response.
    
    Args:
        session_uri (str): The session URI for the resumable upload.
        object_location (str): The path to the local file to resume uploading.
        status_response (Response): The response from the initial upload attempt that returned a 308 status.
    """
    # Retrieve the 'Range' header from the 308 response
    range_header = status_response.headers.get('Range')
    
    if range_header:
        # Extract the last byte uploaded from the Range header
        last_uploaded_byte = int(range_header.split('-')[1])
        next_byte = last_uploaded_byte + 1
        print(f"Resuming upload from byte {next_byte}")
    else:
        # If no Range header, start from the beginning
        print("No range header, starting from the beginning")
        upload_file_to_gcs(object_location, session_uri)
        return 

    # Calculate the remaining bytes to upload
    total_file_size = os.path.getsize(object_location)
    upload_size_remaining = total_file_size - next_byte

    # Prepare headers for the resumed upload
    headers = {
        'Content-Length': str(upload_size_remaining),
        'Content-Range': f'bytes {next_byte}-{total_file_size - 1}/{total_file_size}'
    }

    # Open the file and seek to the next byte to upload
    with open(object_location, 'rb') as f:
        f.seek(next_byte)  # Seek to the byte where we left off
        upload_response = requests.put(session_uri, data=f, headers=headers)

    # Check the upload response
    if upload_response.status_code in (200, 201):
        print("Upload successfully resumed and completed!")
    else:
        print(f"Failed to resume upload: {upload_response.status_code}")
        print(upload_response.text)

def validate_upload_route(session_uri, timeout=5):
    """
    Validates an upload route by checking if the session URI is reachable and ready for use.

    Args:
        session_uri (str): The session URI for the resumable upload.
        timeout (int): The timeout period for the request, in seconds. Default is 5 seconds.

    Returns:
        dict: A dictionary indicating the validation status and any additional information.
    """
    try:
        # Send a HEAD request to check if the session URI is reachable
        response = requests.head(session_uri, timeout=timeout)
        # Check for successful connection
        if response.status_code == 405:
            return True
        else:
            return False
    except requests.exceptions.Timeout:
        return False
    except requests.exceptions.RequestException as e:
        return False

def upload_videos_in_directory(session_uris, directory_path):
    """
    Iterates through each video file in a specified directory and uploads them using the
    upload_file_to_gcs() function, with each file being uploaded to a different URL from session_uris.

    Args:
        session_uris (list): A list of session URIs (URLs) for uploading.
        directory_path (str): The path to the directory containing video files.
    """
    if not os.path.exists(directory_path):
        print(f"Directory {directory_path} does not exist.")
        return

    # Get a list of video files in the directory
    video_files = [file_name for file_name in os.listdir(directory_path)
                   if os.path.isfile(os.path.join(directory_path, file_name)) and file_name.lower().endswith(('.mp4', '.mkv', '.avi', '.mov'))]

    # Check if the number of session URIs matches the number of video files
    if len(session_uris) != len(video_files):
        print(f"Warning: The number of session URIs ({len(session_uris)}) does not match the number of video files ({len(video_files)}).")
        return

    # Loop through each video file and its corresponding session URI
    i = 1
    for file_name, session_uri in zip(video_files, session_uris):
        file_path = os.path.join(directory_path, file_name)
        print(f"Uploading file {i}/{len(session_uris)}")
        i = i+1
        # Call the upload function for each file
        upload_file_to_gcs(file_path, session_uri)

def test():
    file_path = r'C:\Users\Tiago Jesus\Videos\teste.avi'
    session_uri = "https://storage.googleapis.com/upload/storage/v1/b/directus-storage-dev/o?uploadType=resumable&name=41-1e566681-9f24-4e79-a617-bcd670cd951c&upload_id=AHmUCY0rUndK1hCIcx3SLL_fGEIv_QlpUtXL62wp47_z1ToZbuuzwvtDAMoyJbtQ9vAjg3jFypZGkxIp6gMP4M45UgUujeJtwv8WjHSQnW-nNbAvPA"
    result = check_upload_status(session_uri)
    print(result)

    upload_file_to_gcs(file_path, session_uri)

    result = check_upload_status(session_uri)
    print(result)