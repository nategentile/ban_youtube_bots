# Change here the script configuration before running

# Set True to set all the spam comments as "Rejected" and ban the user instead of deleting them
# Set False to ask the API to delete the messages
MODERATE = True
# How many videos you want to check, if you set 1, only the last video will be checked, set 5 for the last five and so
LAST_N_VIDEOS = 20
# If set to True, it will request all the videos from the main playlist, set False to avoid the request and use
# the cached list of videos
CHECK_FOR_NEW_VIDEOS = True
# If set to True, it will request all the comments for all the videos, set False to avoid reloading the comments and
# use the caches list of comments
CHECK_FOR_NEW_COMMENTS = True
# If set to True, it will check for users that have the same profile picture.
# You must put the profile picture in storage/profile_pic.jpg
CHECK_FOR_PROFILE_PICTURE = False
# Set to True to fake all the requests to the Youtube API, it's useful to test something fast without consuming quota
TEST_MODE = False
# If set to True, the script will never ask you for anything, it runs by itself
UNATTENDED = True
# For normal use, set to 20
# 10 = DEBUG, 20 = INFO, 30 = WARNING, 40 = ERROR
LOG_LEVEL = 20


# Put here your channel URL
MY_CHANNEL_URL = ''
# Put here a playlist id with all the videos you want to clean
# Playlist id can be found in the URL of the playlist, for example: https://www.youtube.com/playlist?list=PL6gx4Cwl9DGAj_Q-xgJzDQYZr-QSjS5sY
PLAYLIST_UPLOADS_ID = ''

# Put in this list all the words you want to search in the username of the comment to ban
name_banned_words = ["telegram", "whatsapp", "elegra", "hatsap", "nate gentile", "nate_gentile", "⓪", "①", "②", "③",
                     "④", "⑤", "⑥", "⑦", "⑧", "⑨", "➀", "➁", "➂", "➃", "➄", "➅", "➆", "➇", "➈", "➉"]
# Put in this list all the words you want to search in the message of the comment to ban
body_banned_words = []

# Don't touch this
SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"