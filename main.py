"""
@author Nate Gentile <nate@nategentile.com>
"""
import os
import pickle
import numpy as np
from PIL import Image
from google.auth.transport.requests import Request
import googleapiclient.discovery
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import requests
import skimage
import logging
import config

original_nate_image = Image.open("storage/nate.jpg")


def check_is_spam(message):
    # Check if it's me
    message = message["snippet"]
    if message['authorChannelUrl'] == config.MY_CHANNEL_URL:
        return False
    # Check banned words in comment
    for word in config.name_banned_words:
        if message["authorDisplayName"].lower().find(word) != -1:
            return True

    for word in config.body_banned_words:
        if message["textOriginal"].lower().find(word) != -1:
            return True

    # Check if profile image is the same as my image
    try:
        logging.debug("Downloading image for user profile: {}".format(message["authorProfileImageUrl"]))
        data = requests.get(message["authorProfileImageUrl"]).content
        with open('storage/impostor.jpg', 'wb') as handle:
            handle.write(data)

        impostor = Image.open('storage/impostor.jpg')
        nate_resized_image = original_nate_image.resize((impostor.size[0], impostor.size[1]))

        with open('storage/nate_resized.jpg', 'wb') as handle:
            nate_resized_image.save(handle)

        difference = skimage.metrics.structural_similarity(np.asfarray(impostor.convert('L')),
                                                           np.asfarray(nate_resized_image.convert('L')))

        logging.debug("Difference score from my profile pic is {}".format(difference))
        if difference > 0.8:
            with open('impostors/{}.jpg'.format(message["authorChannelId"]["value"]), 'wb') as handle:
                impostor.save(handle)
            return True
        return False
    except Exception:  # Too broad, but I don't have time for this
        return False


def get_them_all(api_function, api_kwargs, key_path, value_path, prepopulated_list=[]):
    next_page_token = " "
    stuff = {}
    key_path_repeated = False

    while next_page_token and not key_path_repeated:
        api_kwargs["pageToken"] = next_page_token.strip()
        yt_request = api_function().list(**api_kwargs)

        yt_response = execute_youtube_query(yt_request)

        for item in yt_response["items"]:
            current_key = item
            for key in key_path:
                current_key = current_key[key]

            current_value = item
            for key in value_path:
                current_value = current_value[key]

            if current_key in prepopulated_list:
                key_path_repeated = True
                break

            stuff[current_key] = current_value

        next_page_token = yt_response.get("nextPageToken", None)
    return stuff


def get_credentials():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', config.SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', config.SCOPES)
            creds = flow.run_local_server(port=2725)
        # Save the credentials for the next time
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds


def load_from_storage(file_name, default_value):
    if os.path.exists(file_name):
        with open(file_name, 'rb') as handle:
            return pickle.load(handle)
    else:
        return default_value


def save_into_storage(file_name, data):
    with open(file_name, 'wb') as handle:
        pickle.dump(data, handle, protocol=pickle.HIGHEST_PROTOCOL)


def check_new_comments(youtube, videos):
    comment_threads = load_from_storage('storage/comments.pickle', {})

    if config.CHECK_FOR_NEW_COMMENTS:
        current_video = 0
        logging.info("\n- Checking last {} videos\n".format(config.LAST_N_VIDEOS))
        for video_id in videos.keys():
            if video_id not in ['kVG4Ckq3xKQ', 'pfECL23vS5E', '9RJsaeVFvro']:
                logging.info("CURRENT VIDEO IS: {}".format(videos[video_id]))
                logging.info("Checking for new comments...")
                if video_id not in comment_threads:
                    comment_threads[video_id] = {}

                new_comments = get_them_all(
                    youtube.commentThreads,
                    {"part": ["snippet", "replies"],
                     "videoId": video_id,
                     "order": "time",
                     "maxResults": 100},
                    ["snippet", "topLevelComment", "id"],
                    [])

                if len(new_comments) > 0:
                    logging.info("Adding {} new comments\n".format(len(new_comments)))
                else:
                    logging.info("No new comments\n")

                for key in new_comments.keys():
                    comment_threads[video_id][key] = {
                        key: new_comments[key]["snippet"]["topLevelComment"]["snippet"],
                        "responses": new_comments[key].get("replies", {"comments": []})["comments"]
                    }

                current_video += 1

                if current_video == config.LAST_N_VIDEOS:
                    break

        save_into_storage('storage/comments.pickle', comment_threads)
    return comment_threads


def comment_purge_paginated(youtube, to_delete_comments_id, deleted):
    current_page = 0
    page_size = 25

    while current_page < len(to_delete_comments_id) / page_size:
        try:
            paginated_items = [a for a in to_delete_comments_id[current_page * page_size:(current_page + 1) * page_size]]
            if config.MODERATE:
                action = youtube.comments().setModerationStatus(id=paginated_items, moderationStatus="rejected",
                                                                banAuthor=True)
                logging.info("- Moderation on comments: {}".format(", ".join(paginated_items)))
                execute_youtube_query(action)
            else:
                for item in paginated_items:
                    action = youtube.comments().delete(id=item)
                    logging.info("Deletion request to youtube for {}".format(item))
                    execute_youtube_query(action)

            deleted.extend(paginated_items)
            save_into_storage('storage/deleted.pickle', deleted)
        except Exception:  # I know, is too broad, but I don't have time
            logging.info("DELETION FAILED for some comments...")
        current_page += 1


def check_comments_for_spam(comments, deleted):
    to_delete = []
    # Checking spam
    for key, comment in comments.items():
        for reply in comment["responses"]:
            if check_is_spam(reply):
                to_delete.append(reply)
    logging.info("{} spam comments detected".format(len(to_delete)))

    to_delete_comments_id = []
    if config.UNATTENDED:
        show_comments = True
    else:
        show_comments = input("Show comments to delete? [y/n]")

    # Show & gather all the comments into a list, check if not deleted previously
    for comment in to_delete:
        if comment["id"] not in deleted:
            to_delete_comments_id.append(comment["id"])
            if show_comments == "y":
                logging.info("{}: {}".format(comment["snippet"]["authorDisplayName"], comment["snippet"]["textOriginal"]))
        else:
            logging.info("Comment {} was already deleted!".format(comment["id"]))

    if not config.UNATTENDED:
        input("Press Enter to continue...")
    return to_delete_comments_id


def check_new_videos(youtube):
    # Loading previously stored videos
    videos = load_from_storage('storage/videos.pickle', {})

    if config.CHECK_FOR_NEW_VIDEOS:
        logging.info("Checking for new videos")
        new_videos = get_them_all(youtube.playlistItems, {"part": "snippet",
                                                          "playlistId": config.PLAYLIST_UPLOADS_ID,
                                                          "maxResults": 100},
                                  ["snippet", "resourceId", "videoId"], ["snippet", "title"], videos.keys())

        if len(new_videos) > 0:
            logging.info("Adding {} new videos\n".format(len(new_videos)))
            for key, val in new_videos.items():
                videos[key] = val
        else:
            logging.info("No new videos\n")
        save_into_storage('storage/videos.pickle', videos)

    return videos


def execute_youtube_query(query):
    if not config.TEST_MODE:
        logging.debug("Making query to Youtube API")
        return query.execute()
    else:
        logging.debug("Mocked query to Youtube API (No request were made)")
        return {"items": {}}


def main():
    logging.basicConfig(filename="logfile.txt",
                        format="%(asctime)s %(message)s",
                        filemode="w",
                        level=config.LOG_LEVEL)

    logging.getLogger().addHandler(logging.StreamHandler())

    logging.info("-- YOUTUBE SPAM CHECKER RUNNING --\n")

    creds = get_credentials()
    logging.info("Authorized into Youtube")

    # Create API client
    youtube = googleapiclient.discovery.build(config.API_SERVICE_NAME, config.API_VERSION, credentials=creds)

    videos = check_new_videos(youtube)
    comment_threads = check_new_comments(youtube, videos)

    logging.info("Loading previously deleted comments")
    deleted = load_from_storage('storage/deleted.pickle', [])
    logging.info("We deleted {} yet!".format(len(deleted)))

    current_video = 0

    logging.info("\n- Starting spam checks\n")
    for video_key, comments in comment_threads.items():
        logging.info("\nCURRENT VIDEO IS: {}".format(videos[video_key]))
        logging.info("Checking spam comments\n")

        to_delete_comments_id = check_comments_for_spam(comments, deleted)
        comment_purge_paginated(youtube, to_delete_comments_id, deleted)

        current_video += 1

        if current_video == config.LAST_N_VIDEOS:
            break


if __name__ == '__main__':
    main()
