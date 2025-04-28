# this is the main web application file
# this file is responsible for handling the web requests and responses
from flask import Flask, render_template, request, redirect, url_for, session
from zoneinfo import available_timezones
import database as db
from datetime import timedelta

app = Flask(__name__)
# these are the secret key just like in Angus's tutorial for the sessions.
# it should usually be stored not in the code, but in an environment variable or a file, but for simplicity I'm just storing it in the code.
# this thing is used to encrypt the session cookies in symmetric encryption.
app.secret_key = "2391c7975fd2ad630c040819c2354c36e3ad95365cebaa8cefcc326b2ed3526d"
# this means the session will be expired after 30 days, so then the user will have to log in again.
app.permanent_session_lifetime = timedelta(days=30)

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/login", methods=["GET"])
def login():
    # the login page doesn't take an error anymore, but I'm keeping it here for now in case something breaks.
    return render_template("login.html", error=None)

@app.route("/login", methods=["POST"])
def handle_login():
    username = request.form["username"]
    password = request.form["password"]

    success, result = db.validateLogin(username, password)
    if success:
        # this makes the session last for longer than a normal session (normal sessions just last until the browser tab is closed)
        session.permanent = True
        # this session dependency stores the username in the session cookie, and it's automatically encrypted.
        session["username"] = result
        # nothing from the user ever goes into the redirects, to prevent invalid forwarding and redirect attacks.
        return redirect(url_for("dashboard"))
    else:
        return render_template("login.html", message=result)

# sign up page route
@app.route("/signup", methods=["GET"])
def signup():
    return render_template("signup.html", timezones=sorted(available_timezones()))

# handle sign up, all these handle routes are useful to connect the JS/HTML to the database.
@app.route("/signup", methods=["POST"])
def handle_signup():
    # these get the data from the request body
    username = request.form["username"]
    password = request.form["password"]
    confirm_password = request.form["confirm_password"]
    timezone = request.form["timezone"]

    if password != confirm_password:
        return render_template("error.html", message="Passwords do not match.")

    # creatUser has another layer of validation so it's safe, and this function won't need to check the username and stuff.
    success, message = db.createUser(username, password, timezone)
    if not success:
        return render_template("error.html", message=message)

    return redirect(url_for("login"))

# this route is used to connect the database.py functions to the JS/HTML, allowing the user to get live feedback on whether their username is taken.
@app.route("/check_username")
def check_username():
    username = request.args.get("username", "")
    usernames = db.getAllUsernames()
    return {"exists": username in usernames}

# this route has the purpose the same as the previous one, but for the activity names.
@app.route("/check_activity_name")
def check_activity_name():

    # this function just says the username already exists if it can't get a hand on the the username of the user, so make sure there won't be duplicates, so they don't guess if the activity is in there or not. on second thought maybe this should redirect the guy or raise an error. but I won't change it now in case it breaks it.
    if "username" not in session:
        return {"exists": True}

    username = session["username"]
    name = request.args.get("name", "")
    user_id = db.getUserID(username)
    existing_names = db.getAllActivityNamesForUser(user_id)
    return {"exists": name.strip() in existing_names}

@app.route("/logs")
def logs():
    if "username" not in session:
        return redirect(url_for("login"))
    username = session["username"]
    user_id = db.getUserID(username)
    activity_names = db.getAllActivityNamesForUser(user_id)
    has_logged_today = db.userHasLoggedToday(user_id)
    local_date = db.getLocalDateForUser(user_id)
    if has_logged_today:
        return render_template("no_log.html", username=username, date=local_date)
    else:
        return render_template("logs.html", username=username, date=local_date, activities=activity_names)

# this connects the database.py getPieChartDistributionForPeriod function to the chart.js dependency in the JS/HTML.
@app.route("/get_distribution")
def get_distribution():
    # again I have no idea why I decided to return a blank pie chart instead of redirecting the user to login or raising an error. but I won't change it now in case it breaks it. flask still looks foreign. better not make it mad.
    if "username" not in session:
        return {"labels": [], "values": []}
    
    username = session["username"]
    user_id = db.getUserID(username)

    try:
        days = int(request.args.get("days", 0))
        chart_data = db.getPieChartDistributionForPeriod(user_id, days)
        return {
            "labels": list(chart_data.keys()),
            "values": list(chart_data.values())
        }
    except:
        return {"labels": [], "values": []}

@app.route("/get_activity_minutes")
def get_activity_minutes():
    if "username" not in session:
        return {"labels": [], "values": []}

    username = session["username"]
    user_id = db.getUserID(username)

    # the request.args is the data from the request body when it's not using a form and it is a dictionary.
    activity = request.args.get("activity", "").strip()
    if not activity:
        return {"labels": [], "values": []}

    try:
        labels, values = db.getDailyActivityMinutes(user_id, activity)
        return {"labels": labels, "values": values}
    except:
        return {"labels": [], "values": []}

# writing this took hours, I'm not even kidding.
# it looks easy from how short it is (and from how spaghetti the script looks), but the charts and the libraries sometimes just don't like each other and I got to get it all to fix itself.
@app.route("/stats")
def stats():
    # i have finally remembered to direct the user to the login
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]
    user_id = db.getUserID(username)

    # this is for the newbie users.
    has_any_events = db.userHasAnyEvents(user_id)
    if not has_any_events:
        return render_template("no_info_stats.html", username=username)

    # this for the pie chart showing the current day distribution
    chart_data = db.getPieChartDistributionForPeriod(user_id, 1)
    activity_summary = list(chart_data.items())

    # the sleep and quality insights bar charts.
    sleep_labels, sleep_values = db.getSleepHoursLastWeek(user_id)
    quality_labels, quality_values = db.getDailyQualityScores(user_id)

    # this is for that all time distribution pie chart tho I removed it from the actual production though it's still there because I tried to hard to get it to work but gave up because it was taking too long and I had to move on to CSS and stuff. I just hid it in the HTML. I didn't want to delete so much work.
    all_time_data = db.getPieChartDistributionForPeriod(user_id, 0)

    all_activity_names = db.getAllActivityNamesForUser(user_id)

    # this is used to determine whether to show the daily insights
    has_logged_today = db.userHasLoggedToday(user_id)
    # this one's used to see if I gotta show the past week's insights
    has_logged_in_past_week = db.userHasLoggedInThePast_Days(user_id, 6)

    return render_template("stats.html", username=username, # not used
                           has_logged_today=has_logged_today, # flag
                           has_logged_in_past_week=has_logged_in_past_week, # flag
                           labels=list(chart_data.keys()), # pie chart
                           values=list(chart_data.values()), # pie chart
                           activity_summary=activity_summary, # info box
                           sleep_labels=sleep_labels, # sleep insights bar chart
                           sleep_values=sleep_values, # sleep insights bar chart
                           quality_labels=quality_labels, # quality insights bar chart
                           quality_values=quality_values, # quality insights bar chart
                           initial_distribution=all_time_data, # the pie chart that got cut
                           activity_names=all_activity_names) # for the select box in the activity insights

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/add_activity", methods=["POST"])
def add_activity():
    if "username" not in session:
        return {"success": False, "message": "Not logged in."}

    username = session["username"]
    # this gets the name of the acttivity and it will be defaulted to a blank string if the user doesn't enter anything. It should actually raise an error but I had the concept of "get it done fast" and "mitigate errors" in my mind when I made this.
    name = request.form.get("name", "").strip()
    # this gets the boolean value of the isGood checkbox, if it's not checked it'll be false.
    is_good = request.form.get("isGood", "false") == "true"

    try:
        user_id = db.getUserID(username)
        success, result = db.addActivity(user_id, name, is_good)

        if not success:
            return {"success": False, "message": result}

        updated_activities = db.getAllActivityNamesForUser(user_id)
        # this tells the JS/HTMl the stuff to update the activities selector with afterward.
        return {"success": True, "activities": updated_activities, "selected": name}

    except Exception as e:
        return {"success": False, "message": "Something went wrong on the server."}
    
@app.route("/error")
def error():
    # if the message doens't exist it defaults to "An unexpected error occurred.", but I don't use the message thing anymore, but I'll just leave it there.
    msg = request.args.get("message", "An unexpected error occurred.")
    return render_template("error.html", message=msg)

@app.route("/submit_log", methods=["POST"])
def submit_log():
    if "username" not in session:
        return {"success": False, "message": "Not logged in."}

    username = session["username"]
    user_id = db.getUserID(username)

    try:
        # I really should have made these raise errors instead of having a default. But the add event function validates it anyway. So it's fine.
        # cuz it was a string that was passed in:
        data = request.get_json()
        events = data.get("events", [])
        sleep_start = data.get("sleep", "").strip()
        sleep_end = data.get("wake", "").strip()

        failures = []

        # Handle regular events
        for ev in events:
            success, msg = db.addEvent(user_id, ev["start"], ev["end"], ev["activity"])
            if not success:
                failures.append(f"Event ({ev['start']} - {ev['end']}): {msg}")

        # Handle sleep event (passed as 'Sleep' activity)
        success, msg = db.addEvent(user_id, sleep_start, sleep_end, "Sleep")
        if not success:
            failures.append(f"Sleep event: {msg}")

        # I'm actually not using the message anymore, because I thought of something better: I'd just make the finish log button disabled until it's good. But I'll leave it here incase someone managed to bypass that.
        if failures:
            return {"success": False, "message": "; ".join(failures)}

        return {"success": True}

    except Exception as e:
        return {"success": False, "message": "Server error occurred."}

@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    username = session["username"]
    user_id = db.getUserID(username)

    # used for the pie chart
    chart_data = db.getPieChartDistributionForPeriod(user_id, 30)
    # used for that box with the activities and how much time spent on them
    activity_summary = list(chart_data.items())
    
    # these are for the notifications
    days_tracked = db.getDaysSinceAccountCreation(user_id)
    has_logged_today = db.userHasLoggedToday(user_id)
    streak = db.getStreakLoggedDays(user_id)

    # this one determins if the user is a newbie or not
    has_any_events = db.userHasAnyEvents(user_id)

    if not has_any_events:
        # this renders that page with the welcome message
        return render_template("no_info_dashboard.html", username=username)

    # since all that's shown is the month summary, this would need to be passed in because if there was no data for the month the charts woudn't render well.
    logged_this_month = db.userHasLoggedInThePast_Days(user_id, 30)
    return render_template("dashboard.html", username=username, logged_this_month=logged_this_month,
                       labels=list(chart_data.keys()), # pie chart
                       values=list(chart_data.values()), # pie chart
                       activity_summary=activity_summary, # info box
                       days_tracked=days_tracked, # notifications
                       logged=has_logged_today, # notifications
                       streak=streak) # notifications

if __name__ == "__main__":
    # need to set the default to 0.0.0.0 means any host, so any ip address can connect to it
    app.run(debug=True, port=5000, host="0.0.0.0")