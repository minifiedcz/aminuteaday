# this is the database connection file
# this file is responsible for connecting to the database
# and functions that interface with the database

"""
Functions for handling database interactions.
"""

import sqlite3
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, available_timezones
import hashlib
import re

DATABASE_FILE = "aminuteaday.db"

#HELPER FUNCTIONS - I don't use these in the main.py, these are just here to skip redundancy
# I used the varName: datatype -> returnDataType, this helps reduce errors and confusion in a bigger project. I didn't realise it'll get so complex but it did.
def UTCToLocal(utc_dt: datetime, user_timezone: str) -> datetime:
    """
    Converts a UTC datetime to the user's local time.
    Requires:
    - utc_dt: a timezone-aware datetime in UTC.
    Returns:
    - A timezone-aware datetime in the user's local time.
    """
    return utc_dt.astimezone(ZoneInfo(user_timezone))

def localToUTC(local_dt: datetime) -> datetime:
    """
    Converts a timezone-aware local datetime into UTC.
    Requires:
    - local_dt: a timezone-aware datetime in local time.
    Returns:
    - A timezone-aware datetime in UTC.
    """
    return local_dt.astimezone(ZoneInfo("UTC"))

def ISOToDatetime(iso_string: str) -> datetime:
    """
    Converts an ISO 8601 string from the database into a timezone-aware datetime.
    This is used when reading datetime strings from SQLite (that include timezone info: '+00:00').
    Parameters:
    - iso_string: A string like "2025-04-18T12:00:00+00:00"
    Returns:
    - A timezone-aware datetime object.
    """
    dt = datetime.fromisoformat(iso_string)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt

def DatetimeToISO(utc_dt: datetime) -> str:
    """
    Converts a UTC datetime object into an ISO 8601 string for database storage.
    Requires:
        - utc_dt: a timezone-aware datetime with tzinfo set to UTC.
    Returns:
        - A string like "2025-04-18T12:00:00+00:00"
    """
    if utc_dt.tzinfo != ZoneInfo("UTC"):
        raise ValueError("Datetime must have UTC timezone (tzinfo=ZoneInfo('UTC'))")
    return utc_dt.isoformat()

# EXPORTED FUNCTIONS - mostly, though after a while I started adding stuff in rushed production, so some of these ones are actually helper functions
def getMinutesSpentOverTimePeriod(userID: int, activityID: int, days: int) -> int:
    """
    Calculates total minutes a user has spent on a specific activity since 12AM a certain number of days ago. E.g. if days == 1, it will be since 12AM on the current day.
    days == 0 means get data for all time.
    """
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()

    c.execute("SELECT timezone FROM Users WHERE userID = ?", (userID,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise ValueError(f"userID {userID} not found.")
    user_timezone = row[0]

    current_time_utc = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))

    if days > 0:
        current_time_local = UTCToLocal(current_time_utc, user_timezone)
        local_midnight = datetime.combine(current_time_local.date(), datetime.min.time(), tzinfo=ZoneInfo(user_timezone))
        start_boundary_local = local_midnight - timedelta(days=days - 1)
        start_boundary_utc = localToUTC(start_boundary_local)
    else:
        start_boundary_utc = datetime.min.replace(tzinfo=ZoneInfo("UTC"))
        # This one is for the all time

    end_boundary_utc = current_time_utc

    c.execute("""
        SELECT startTime, endTime FROM Events
        WHERE userID = ? AND activityID = ?
        AND endTime >= ? AND startTime <= ?
    """, (userID, activityID, DatetimeToISO(start_boundary_utc), DatetimeToISO(end_boundary_utc)))
    events = c.fetchall()
    conn.close()

    total_minutes = 0
    for start, end in events:
        start = ISOToDatetime(start)
        end = ISOToDatetime(end)
        # this part looks confusing but it's actually just a smart way to do it that I'm proud of. This ensures that events that are between two days can be counted too, but only the bit of the event that is in the day. See below: :)
        effective_start = max(start, start_boundary_utc)
        effective_end = min(end, end_boundary_utc)

        if effective_end > effective_start:
            duration_mins = math.ceil((effective_end.timestamp() - effective_start.timestamp()) / 60)
            total_minutes += duration_mins

    return total_minutes

# This function was used to prevent duplicate usernames in the signup page
def getAllUsernames() -> list[str]:
    """
    Returns a list of all usernames currently registered.
    """
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT username FROM Users")
    usernames = [row[0] for row in c.fetchall()]
    conn.close()
    return usernames

def createUser(username: str, password: str, timezone: str) -> tuple[bool, str]:
    """
    Attempts to create a new user. Returns (success, message) if successful.
    Returns (False, err_msg) if failed.
    Handles validation internally so the client can't bypass it.
    """
    # this full backend system double checks the validity of the stuff passed in from the frontend, because the client can tamper with the scripts there, as I will show (or have already shown) in my presentation

    # regex for a username that is 3-20 characters long, and no symbols except for one dash OR underscore and no spaces
    if not re.fullmatch(r"^(?!.*[-_].*[-_])[a-zA-Z0-9_-]{3,20}$", username):
        return False, "Invalid username format."

    if timezone not in available_timezones():
        return False, "Invalid timezone."

    # regex for a password that's 8-20 characters long, and has at least one lowercase letter, one uppercase letter, one number, and one symbol
    if not re.fullmatch(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w\s]).{8,}$", password):
        return False, "Password does not meet security requirements."

    if username in getAllUsernames():
        return False, "Username already exists."

    # copy pasted some stuff fron angus's tutorial todo app, but the TOTP code was too hard and tedious so I gave up on that bit. At least the hashing is still here.
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    creation_utc = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))
    creation_iso = DatetimeToISO(creation_utc)

    # I remembered the question mark format from when it was taught in SSA in class. So it can prevent SQL injection.
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO Users (username, passwordHash, accountCreationDate, timezone)
        VALUES (?, ?, ?, ?)
    """, (username, password_hash, creation_iso, timezone))
    conn.commit()
    conn.close()

    # the string part in here isn't really used, but I got to keep it there because it has to return a tuple with a bool and a string
    # later on I actually cut the need for the error message string entirely, because on second thought, I realised telling the user EXACTLY what went wrong might actually just be trying to get the program to have a vulnerability of information leakage. So to improve security, I just removed it.
    return True, "Account created successfully."

def validateLogin(username: str, password: str) -> tuple[bool, str]:
    """
    Checks whether the given username and password combination is valid.
    Returns (True, username) if correct, or (False, error_message) if not.
    """
    # this try and except over the whole thing is good. I really should've done this to all the functions before, but at this point I had already realised how big this project is and I was running out of time. Luckily it's just a prototype, and it's good enough that it looks great from the frontend and works well.
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        c = conn.cursor()
        c.execute("SELECT passwordHash FROM Users WHERE username = ?", (username,))
        row = c.fetchone()
        conn.close()

        if not row:
            return False, "Username or password is not correct."

        # I hash this to compare the hashes. Because the same thing always hashes into the same hash.
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if row[0] == password_hash:
            return True, username
        else:
            return False, "Username or password is not correct."
    
    except Exception as e:
        return False, "An error occurred."
    
def addActivity(userID: int, activityName: str, isGood: bool) -> tuple[bool, str | int]:
    """
    Adds a new activity to the Activities table for the given user.

    Returns:
        (True, activityID) if successful,
        (False, errorMessage) if failed.
    """
    try:
        activityName = activityName.strip()

        if not activityName:
            return False, "Activity name cannot be blank."

        if not re.fullmatch(r"[a-zA-Z0-9 ]+", activityName):
            return False, "Activity name can only contain letters, numbers, and spaces."

        if len(activityName) > 20:
            return False, "Activity name must be 20 characters or fewer."

        # this part makes sure that each user never has two activities with the same name. I'd considered making the activity name UNIQUE in the database SQL, but then I realised that that would prevent two DIFFERENT users from having activities with the same name, which isn't what I want.
        conn = sqlite3.connect(DATABASE_FILE)
        c = conn.cursor()
        c.execute("SELECT 1 FROM Activities WHERE userID = ? AND activityName = ?", (userID, activityName))
        if c.fetchone():
            conn.close()
            return False, "You already have an activity with that name."

        c.execute("""
            INSERT INTO Activities (userID, activityName, isGood)
            VALUES (?, ?, ?)
        """, (userID, activityName, isGood))
        conn.commit()
        activity_id = c.lastrowid
        conn.close()

        # I was going to use the activityID to get the select to have the default was the new activity, but it wasn't needed, but I didn't want to break anything because I realised this was redundant really later in the project and I just didn't want to break anything at that point
        return True, activity_id

    except Exception as e:
        return False, "An unexpected error occurred while adding the activity."

# this thing was used for the add activity form in the logs.html page. it's used to validate the frontend input, so the user can get feedback in real time if it's correct or not.
def getAllActivityNamesForUser(userID: int) -> list[str]:
    """
    Returns a list of all activity names for a given user.

    Parameters:
        userID (int): The ID of the user.

    Returns:
        list[str]: A list of activity names.
    """
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT activityName FROM Activities WHERE userID = ?", (userID,))
    rows = c.fetchall()
    conn.close()
    # i learned that a for loop actually doesn't need to run multiple lines. I'm proud of this one. (See below)
    return [row[0] for row in rows]

def addEvent(userID: int, startTime: datetime, endTime: datetime, activityID: int) -> None:
    """
    Adds a new event entry to the Events table.

    Parameters:
        userID (int): The ID of the user.
        startTime (datetime): The UTC datetime when the event started.
        endTime (datetime): The UTC datetime when the event ended.
        activityID (int): The activity ID (0 for sleep).
    """
    if startTime >= endTime:
        raise ValueError("Start time must be before end time.")

    start_iso = DatetimeToISO(startTime)
    end_iso = DatetimeToISO(endTime)

    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO Events (userID, activityID, startTime, endTime)
        VALUES (?, ?, ?, ?)
    """, (userID, activityID, start_iso, end_iso))
    conn.commit()
    # you will never imagine how many times I forgot to close this thing.
    conn.close()

# I figured it wouldn't be good to have the userID passed around in the frontend because you always want to have the least information given out there as possible (SSA concept), so I always made the frontend communicate with username, and then the backend would translate it and then do the stuff. 
def getUserID(username: str) -> int:
    """
    Returns the userID for a given username.
    
    Parameters:
        username (str): The username to look up.

    Returns:
        int: The user's ID.
    
    Raises:
        ValueError: If the username does not exist.
    """
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT userID FROM Users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()

    if row:
        return row[0]
    else:
        # fstrings would be fine here, besides I can't use the question mark format here because it's not a SQL query. But since it's not a query, it's safe to put it there, because it's already a string that's not getting executed anyway. And the username would have been sanitized before it got here.
        raise ValueError(f"Username '{username}' not found.")

def addEvent(userID: int, start_str: str, end_str: str, activityName: str) -> tuple[bool, str]:
    # I realised at the end of production after everything was done that I had two duplicate addEvent functions. I must have forgot to delete the old one when coding the new one, because I always copy paste the old one and edit one of them for no-risk, and then I forgot to delete the old one. It works somehow, but I'm not going to delete any because I don't want to break anything.
    # at this point the DOCStrings were getting tedious but I really did need them when coding it because it's hard having to keep flicking back to the function to see what it needs. So the DOCStrings are a lot of them copy and pasted parts, which I guess is fine.
    """
    Adds a new event entry to the Events table with backend validation.
    
    Parameters:
        userID (int): The ID of the user.
        start_str (str): Start time as a string in HH:MM AM/PM format.
        end_str (str): End time as a string in HH:MM AM/PM format.
        activityName (str): The selected activity name (must be valid and belong to the user).
    
    Returns:
        tuple: (True, "Success") if added, (False, error message) if failed.
    """
    try:
        # this makes sure that the user actually selected an activity
        if activityName.strip() in ["Add activity", "- select activity -"]:
            return False, "Invalid activity selection."

        # i can't believe now many times I pasted this section of code, I really should've just made a helper function. But it was an intense production (2 and a bit weeks from start to finish, including the weekend before holidays, the holidays and the pupil free day after. It was basically coding non-stop - exhausting but I'm proud of what I learned and made).
        conn = sqlite3.connect(DATABASE_FILE)
        c = conn.cursor()
        c.execute("SELECT timezone FROM Users WHERE userID = ?", (userID,))
        row = c.fetchone()
        if not row:
            conn.close()
            return False, "User not found."
        user_timezone = row[0]

        # this is just a fancy way of having a structure that the string has to follow - kind of like regex I guess.
        # it's just like %s - where it has to be a string.
        # I learned that there's actually other ones too. 
        # %I means hour, %M means minute, %p means AM or PM
        # I can't believe the people who wrote python actually thought of all of this stuff.
        # I'm proud of this one. :D
        time_format = "%I:%M %p"

        # this is a just in case thing to make SURE that the string is a valid format. the frontend already checks it but I can't rely on the client side so I just did the validation again. The strptime I used to be so confused and think it meant "strip time" but it actually means "string parse time"
        try:
            parsed_start = datetime.strptime(start_str.strip(), time_format).time()
            parsed_end = datetime.strptime(end_str.strip(), time_format).time()
            # this part turns the string into a datetime object, and the timeformat tells the datetime object what format the string is in.
            # this part validates the string 
            # It's way better than splitting the string by a space then by a colon and writing a bunch of if statements for validation. Maybe I could remember this for the HSC if something like this comes up.
        except ValueError:
            return False, "Start or end time format is invalid."

        # the main.py doesn't pass in the date, so this function figures out the local date of the user:
        now_utc = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))
        now_local = UTCToLocal(now_utc, user_timezone)
        current_date = now_local.date()

        # I had this time when I entered 1AM for sleep (it's unbelievable how late I had to sleep sometimes to finish this, so I do hope I get 100% if you read this comment)
        # and then another time I wrote 9:00PM for sleep, which meant the event went over a day. And that one didn't calculate properly because the start time 9:00PM was BEFORE the end time 8:00 AM.
        # so I made this part to make sure that it's handled properly, for both when sleep goes overnight, and when it doesn't.
        start_dt_local = datetime.combine(current_date, parsed_start, tzinfo=ZoneInfo(user_timezone))
        # this part connects a date: YYYY-MM-DD with a time: HH:MM:SS with a timezone (user timezone, +10:00 for sydney right now)
        end_dt_local = datetime.combine(current_date, parsed_end, tzinfo=ZoneInfo(user_timezone))
        if activityName == "Sleep":
            # this part is for when the sleep doesn't go overnight. it changes it to the previous day. so then it would correctly be 9:00 PM yesterday to 8:00 AM today.
            start_dt_local = start_dt_local - timedelta(days=1)
        if end_dt_local <= start_dt_local:
            # this part addresses when the sleep DOES go overnight and for all the other activies.
            end_dt_local += timedelta(days=1)
        else:
            if end_dt_local <= start_dt_local:
                end_dt_local += timedelta(days=1)
                # this part is for when sleep DOESN'T go overnight. Because if it was 1AM to 9AM then the start time was already before the end time, but then before we shifted the start time back a day, which means later on the sleep time would be calculated to be 24 hours MORE than it should be. So I just subtracted a day.

        # converts it to the UTC so it's ready to be put into the database, that stores all UTC
        start_utc = localToUTC(start_dt_local)
        end_utc = localToUTC(end_dt_local)

        # there were just so many start times and end times before, and even I'm confused so I just add this again as a final check. This checks it with the date, which one is later.
        if start_utc >= end_utc:
            return False, "Start time must be before end time."

        # gets the activity ID to insert too (gathering all the data now.)
        if not activityName == "Sleep":
            c.execute("SELECT activityID FROM Activities WHERE userID = ? AND activityName = ?", (userID, activityName))
            row = c.fetchone()
            if not row:
                conn.close()
                return False, "Activity not found for this user."
            activityID = row[0]
        else:
            activityID = 0

        c.execute("""
            INSERT INTO Events (userID, activityID, startTime, endTime)
            VALUES (?, ?, ?, ?)
        """, (userID, activityID, DatetimeToISO(start_utc), DatetimeToISO(end_utc)))
        conn.commit()
        conn.close()

        return True, "Event added successfully."

    except Exception as e:
        return False, "An unexpected error occurred while adding the event."

# this is used for the stats page on whether or not to render the daily info. And also the logs page and the dashboard to determine whether or not to get the user to log their data.
def userHasLoggedToday(userID: int) -> bool:
    """
    Returns True if the user has at least one event that both starts and ends
    within today's date (in their local timezone). Otherwise False.
    """
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()

    # yep, there it is again. another copy paste of the timezone script.
    c.execute("SELECT timezone FROM Users WHERE userID = ?", (userID,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False
    user_timezone = row[0]

    # this one gets the start and end time of the local user day, and then gets that into UTC. because a UTC might have a different time to the user's day, which would mess things up, so this bit clears the shift between UTC time and the user's local time
    now_utc = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))
    now_local = UTCToLocal(now_utc, user_timezone)
    today_start_local = datetime.combine(now_local.date(), datetime.min.time(), tzinfo=ZoneInfo(user_timezone))
    today_end_local   = datetime.combine(now_local.date(), datetime.max.time(), tzinfo=ZoneInfo(user_timezone))

    start_utc = localToUTC(today_start_local)
    end_utc   = localToUTC(today_end_local)

    # this one will only count events that are entirely within the day (not crossing overnight ones) this just makes sure that everything works fine, and the user won't be prevented from logging when they haven't logged yet.
    c.execute("""
        SELECT 1 FROM Events
        WHERE userID = ?
          AND startTime >= ?
          AND endTime   <= ?
        LIMIT 1
    """, (userID, DatetimeToISO(start_utc), DatetimeToISO(end_utc)))

    found = c.fetchone() is not None
    conn.close()
    return found

# this one was used to display the date on the logs page.
def getLocalDateForUser(userID: int) -> str:
    """
    Returns the local date for a given user.
    """
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT timezone FROM Users WHERE userID = ?", (userID,))
    row = c.fetchone()
    user_timezone = row[0]
    current_time_utc = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))
    current_time_local = UTCToLocal(current_time_utc, user_timezone)
    return current_time_local.date()

def getPieChartDistributionForPeriod(userID: int, days: int) -> dict[str, int]:
    """
    Returns a dictionary mapping activity names to minutes spent on them over the past `days`.
    Sleep (activityID = 0) is excluded.
    """
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()

    # yep here it is again:
    c.execute("SELECT timezone FROM Users WHERE userID = ?", (userID,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise ValueError(f"userID {userID} not found.")
    user_timezone = row[0]

    # this gets the time range in terms of the days of the user. For the same reason as the userHasLoggedToday function.
    now_utc = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))
    now_local = UTCToLocal(now_utc, user_timezone)
    local_midnight = datetime.combine(now_local.date(), datetime.min.time(), tzinfo=ZoneInfo(user_timezone))
    start_local = local_midnight - timedelta(days=days - 1)
    start_utc = localToUTC(start_local)
    end_utc = start_utc + timedelta(days=days)

    # this gets all the non-sleep activities (activity ID plus name). I don't need to eliminate the ID = 0, because the sleep activity isn't in the database anyway, because it's there by default so it would be redundant
    c.execute("SELECT activityID, activityName FROM Activities WHERE userID = ?", (userID,))
    activities = dict(c.fetchall())  # this turns it into a dictionary of {activityID: name, activityID: name, etc.}

    # this gets all events within the range that was passed in, excluding sleep (activityID 0)
    c.execute("""
        SELECT activityID, startTime, endTime FROM Events
        WHERE userID = ? AND activityID != 0
        AND endTime >= ? AND startTime <= ?
    """, (userID, DatetimeToISO(start_utc), DatetimeToISO(end_utc)))

    # this creates a dictionary like this {"Studying":0, "gaming":0, "sleeping": 0}
    # this thing is just a shorthand that works because the name will be different each time from the forloop iterating in the activities dictionary whos values is the names of the activities. and the 0 stays the same.
    # this dictionary is used because the name of each is the activity and the 0's will be the amount of minutes spent, which is added in later.
    pie_data = {name: 0 for name in activities.values()}

    # this part relies on the order, the first value goes into the activityID the second into start etc. for each tuple in the list that the fetchall returns. Another thing I learned, maybe this will be useful for HSC.
    for activityID, start, end in c.fetchall():
        start_dt = max(ISOToDatetime(start), start_utc)
        end_dt = min(ISOToDatetime(end), end_utc)

        if end_dt > start_dt:
            duration = math.ceil((end_dt - start_dt).total_seconds() / 60)
            name = activities.get(activityID)
            if name:
                pie_data[name] += duration

    conn.close()
    # this part gives a dictionary like "Studying": 100, "Sleeping": 0, "Gaming": 50, etc., but not for the activities that the user didn't do for that period (v<=0)
    return {k: v for k, v in pie_data.items() if v > 0}

# this gets the account age of a user in days, this is used in that "You've used aminute a day for X days" thing in the dashboard.html
def getDaysSinceAccountCreation(userID: int) -> int:
    """
    Returns the number of days since the user's account was created.
    """
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT accountCreationDate FROM Users WHERE userID = ?", (userID,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise ValueError(f"userID {userID} not found.")
    account_creation_date = ISOToDatetime(row[0]).replace(hour=0, minute=0, second=0, microsecond=0)
    days_since_creation = (datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")) - account_creation_date).days
    conn.close()
    # I decided to add 1 so that new users don't get 0 days.
    return days_since_creation + 1

# this is used to determine whether or not the user is new and to show the welcome message in the dashboard. If there's no events then the user would be new, so the no_info_dashbaord.html will be shown instead (though this logic is in main.py)
def userHasAnyEvents(userID: int) -> bool:
    """
    Returns True if the user has logged at least one event, otherwise False.
    """
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM Events WHERE userID = ? LIMIT 1", (userID,))
    result = c.fetchone()
    conn.close()
    return result is not None

# this is used for the sleep insights bar chart.
def getSleepHoursLastWeek(userID: int) -> tuple[list[str], list[float]]:
    """
    Returns two lists of length 7:
      - labels: ['mon','tue',...,'sun'] for the last 7 days *ending yesterday* e.g. the example would be for the monday.
      - values: total hours slept (rounded to 0.1h) assigned to each of those days
                (i.e. a sleep that ends on Wed morning is counted for Tue’s label).
    """
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()

    # again
    c.execute("SELECT timezone FROM Users WHERE userID = ?", (userID,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise ValueError(f"userID {userID} not found")
    user_tz = row[0]

    # find yesterday in the local time cuz it would start from the day before
    now_utc   = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))
    now_local = UTCToLocal(now_utc, user_tz)
    yesterday = now_local.date() - timedelta(days=1)

    # this makes a dictionary of the dates of the past 7 days starting from yesterday.
    window_dates = [yesterday - timedelta(days=i) for i in reversed(range(7))]

    sleep_by_date = { d: 0.0 for d in window_dates }

    c.execute("""
        SELECT startTime, endTime
        FROM Events
        WHERE userID = ? AND activityID = 0
        ORDER BY endTime DESC
        LIMIT 7
    """, (userID,))
    rows = c.fetchall()
    conn.close()

    for start_iso, end_iso in rows:
        start_utc = ISOToDatetime(start_iso)
        end_utc   = ISOToDatetime(end_iso)
        end_loc   = UTCToLocal(end_utc,   user_tz)

        hours = round((end_utc - start_utc).total_seconds() / 3600, 1)

        bucket_date = (end_loc.date() - timedelta(days=1))
        if bucket_date in sleep_by_date:
            sleep_by_date[bucket_date] = hours

    labels = [d.strftime("%a").lower() for d in window_dates]
    values = [sleep_by_date[d] for d in window_dates]

    return labels, values


def getDailyQualityScores(userID: int) -> tuple[list[str], list[int]]:
    """
    Returns a tuple (labels, values) for quality scores of the past 7 days:
    - labels: list of weekday strings ["thu", "fri", ..., "wed"]
    - values: quality scores as percentages (0–100), rounded down

    Quality is defined as:
        floor(100 * minutes_good / minutes_total)
    Excludes sleep (activityID = 0), which isn't good or bad.
    """
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()

    # getting that timezone again...
    c.execute("SELECT timezone FROM Users WHERE userID = ?", (userID,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise ValueError(f"userID {userID} not found.")
    user_timezone = row[0]

    now_utc = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))
    now_local = UTCToLocal(now_utc, user_timezone)

    # this makes a list of (start_utc, end_utc, label) for each day
    # e.g. [('2025-04-20 00:00:00', '2025-04-21 00:00:00', 'sat'), ('2025-04-19 00:00:00', '2025-04-20 00:00:00', 'fri'), ...], the times are the start and end of the day in UTC timezone. Label is the "mon", "tue", etc.
    date_ranges = []
    for i in range(6, -1, -1):
        date = now_local.date() - timedelta(days=i)
        start_local = datetime.combine(date, datetime.min.time(), tzinfo=ZoneInfo(user_timezone))
        end_local = start_local + timedelta(days=1)
        start_utc = localToUTC(start_local)
        end_utc = localToUTC(end_local)
        # strftime means "string from time", so it takes the full UTC datetime and gets the week day string as 3 letters (%a) which would give "mon", "tue", etc. (the opposite of strftime is strptime, which is "string parse time", which i'd already talked about earlier)
        label = date.strftime("%a").lower()
        date_ranges.append((start_utc, end_utc, label))

    # getting the big global start and end times for the query of the events
    start_week = date_ranges[0][0]
    end_week = date_ranges[-1][1]
    c.execute("""
        SELECT activityID, startTime, endTime FROM Events
        WHERE userID = ? AND activityID != 0
        AND endTime > ? AND startTime < ?
    """, (userID, DatetimeToISO(start_week), DatetimeToISO(end_week)))
    # aid stands for activityID, s stands for start, e stands for end.
    events = [(aid, ISOToDatetime(s), ISOToDatetime(e)) for aid, s, e in c.fetchall()]

    # filter out the good activities, so we can add the total minutes of those and divide by the total minutes of the whole thing.
    c.execute("SELECT activityID FROM Activities WHERE userID = ? AND isGood = 1", (userID,))
    good_ids = set(aid for (aid,) in c.fetchall())
    # closing this thing is now hammered in my head, I haven't forgot it in a while now.
    conn.close()

    labels = []
    quality_scores = []

    for start_utc, end_utc, label in date_ranges:
        total = 0
        good = 0

        for aid, ev_start, ev_end in events:
            # this uses the same logic in the getTotalMinutesOverTimePeriod function, in addressing events that cross the time boundaries (ev_start and ev_end).
            overlap_start = max(start_utc, ev_start)
            overlap_end = min(end_utc, ev_end)
            if overlap_end > overlap_start:
                minutes = math.ceil((overlap_end - overlap_start).total_seconds() / 60)
                total += minutes
                if aid in good_ids:
                    good += minutes
            # I wasn't bothered to write the else and raise the error and all that when the data is invalid, I just wanted it done at that point.

        quality = math.floor(100 * good / total) if total > 0 else 0 # just in case we ever get a divide by 0 error :)
        #I guess math comes in handy after all. I've finally seen math in real life after 13 years of schooling.
        labels.append(label)
        quality_scores.append(quality)

    return labels, quality_scores

# this one's for the activity bar chart.
def getDailyActivityMinutes(userID: int, activityName: str) -> tuple[list[str], list[int]]:
    """
    Returns (labels, values) for time spent (in minutes) on a specific activity
    per day over the past week (including today). Labels are lowercase weekdays ("mon", "tue", ...).

    Parameters:
        - userID (int): The ID of the user
        - activityName (str): The name of the activity to filter for (must exist)

    Returns:
        - (labels, values): Tuple of day labels and corresponding minutes spent
    """
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()

    # timezone again
    c.execute("SELECT timezone FROM Users WHERE userID = ?", (userID,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise ValueError("User not found")
    user_timezone = row[0]

    # translate the activity name to it's ID. i didn't pass in the ID in the first place because the select tag in the HTML would have the names in the things, and I just decided to make the values in there match for ease.
    c.execute("SELECT activityID FROM Activities WHERE userID = ? AND activityName = ?", (userID, activityName))
    row = c.fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Activity '{activityName}' not found for this user")
    activityID = row[0]

    now_utc = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))
    now_local = UTCToLocal(now_utc, user_timezone)

    # get the time ranges for each day just like in the getDailyQualityScores function.
    date_ranges = []
    for i in range(6, -1, -1):
        date = now_local.date() - timedelta(days=i)
        start_local = datetime.combine(date, datetime.min.time(), tzinfo=ZoneInfo(user_timezone))
        end_local = start_local + timedelta(days=1)
        date_ranges.append((localToUTC(start_local), localToUTC(end_local), date.strftime("%a").lower()))

    # this gets all the events that match the activityID and the time ranges.
    week_start = date_ranges[0][0]
    week_end = date_ranges[-1][1]
    c.execute("""
        SELECT startTime, endTime FROM Events
        WHERE userID = ? AND activityID = ?
        AND endTime > ? AND startTime < ?
    """, (userID, activityID, DatetimeToISO(week_start), DatetimeToISO(week_end)))
    rows = c.fetchall()
    conn.close()

    # this sorts the events into a list of types where each type is the start time and end time of the event.
    events = [(ISOToDatetime(s), ISOToDatetime(e)) for s, e in rows]
    labels = []
    values = []

    # this is the same logic as in the getDailyQualityScores function.
    for day_start, day_end, label in date_ranges:
        minutes = 0
        for ev_start, ev_end in events:
            overlap_start = max(ev_start, day_start)
            overlap_end = min(ev_end, day_end)
            if overlap_end > overlap_start:
                minutes += math.ceil((overlap_end - overlap_start).total_seconds() / 60)
        labels.append(label)
        values.append(minutes)

    return labels, values

# this one is used to check if the user has logged in the past month on the dashboard.html and whether the user has logged in the past week for the sleep and the quality and the activity bar charts.
def userHasLoggedInThePast_Days(userID: int, days: int) -> bool:
    """
    Returns True if the user has logged in the past `days` days, otherwise False.
    """
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM Events WHERE userID = ? AND startTime > ?", (userID, DatetimeToISO(datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")) - timedelta(days=days))))
    result = c.fetchone()
    conn.close()
    return result is not None

# this is used for the streak thing on the dashboard.html
def getStreakLoggedDays(userID: int) -> int:
    """
    Returns the current streak of consecutive days for which the user
    has logged at least one event fully within that day (so overnight sleep isn't included), in their local timezone.
    """
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()

    # getting the timezone, once more...
    c.execute("SELECT timezone FROM Users WHERE userID = ?", (userID,))
    row = c.fetchone()
    if not row:
        conn.close()
        return 0
    user_timezone = row[0]

    now_utc   = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))
    now_local = UTCToLocal(now_utc, user_timezone)
    today     = now_local.date()

    # this is a helper function that returns the start and end of a day in UTC.
    # it's inside the getStreakLoggedDays function because it's used in the getStreakLoggedDays function, so when getStreakLoggedDays ended scope wise, the day_window function would be gone, and it won't take up space.
    def day_window(date):
        """Return (start_utc, end_utc) for a local-date’s midnight→next-midnight."""
        start_local = datetime.combine(date, datetime.min.time(), tzinfo=ZoneInfo(user_timezone))
        end_local   = start_local + timedelta(days=1)
        return localToUTC(start_local), localToUTC(end_local)

    start_utc, end_utc = day_window(today)
    c.execute("""
        SELECT 1 FROM Events
        WHERE userID = ?
          AND startTime >= ? AND endTime <= ?
        LIMIT 1
    """, (userID, DatetimeToISO(start_utc), DatetimeToISO(end_utc)))
    has_today = c.fetchone() is not None

    # this part is there so that if the user hasn't logged in the current day they're streak won't be reset to 0 and scare them and all that. The streak only cuts if they MISSED a day, but they can't have missed today because they can always still log.
    streak = 1 if has_today else 0

    # this searches from yesterday and then the day before, the day before that, etc. until it finds a day without an event fully inside the day. The offset is counts the number of days to go back in.
    offset = 1
    while True:
        check_date = today - timedelta(days=offset)
        start_utc, end_utc = day_window(check_date)

        c.execute("""
            SELECT 1 FROM Events
            WHERE userID = ?
              AND startTime >= ? AND endTime <= ?
            LIMIT 1
        """, (userID, DatetimeToISO(start_utc), DatetimeToISO(end_utc)))

        if c.fetchone():
            streak += 1
            offset += 1
        else:
            break

    conn.close()
    return streak

    

