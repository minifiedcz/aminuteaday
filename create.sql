CREATE TABLE Users (
    userID INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    passwordHash TEXT NOT NULL,
    accountCreationDate DATETIME NOT NULL,  -- Stored in UTC, YYYY-MM-DDTHH:MM:SS+00:00
    timezone TEXT NOT NULL  -- e.g. 'Australia/Sydney'
);

CREATE TABLE Activities (
    activityID INTEGER PRIMARY KEY AUTOINCREMENT,
    userID INTEGER NOT NULL,
    activityName TEXT NOT NULL,
    isGood BOOLEAN NOT NULL,
    FOREIGN KEY (userID) REFERENCES Users(userID)
);

CREATE TABLE Events (
    eventID INTEGER PRIMARY KEY AUTOINCREMENT,
    userID INTEGER NOT NULL,
    activityID INTEGER NOT NULL,  -- 0 the ID for sleep
    startTime DATETIME NOT NULL,
    endTime DATETIME NOT NULL,
    FOREIGN KEY (userID) REFERENCES Users(userID),
    FOREIGN KEY (activityID) REFERENCES Activities(activityID)
);