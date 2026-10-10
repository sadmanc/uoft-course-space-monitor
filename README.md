# UofT Course Space Monitor

A small Python monitor for University of Toronto Timetable Builder course sections. It checks the Timetable Builder API for enrolment, capacity, waitlist size, and waitlist eligibility. In watch mode it reports changes in the terminal and can send optional alerts through a private ntfy topic.

The monitor only reads the timetable API. It does not sign in to ACORN, join waitlists, or enrol in courses.

## Requirements

- Python 3.10 or newer
- Network access to `api.easi.utoronto.ca`
- Optional: a private ntfy topic for phone notifications

No third-party Python packages are required.

## Find a section

Read the course and section values from Timetable Builder. You will need the full API course code, search title, section name, session code, and division code.

Run one check:

```sh
python3 ttb_seat_monitor.py \
  --course-code ABC123H1 \
  --course-title ABC123 \
  --section LEC0101 \
  --session 20269 \
  --division ARTSC
```

Poll every 30 seconds and send alerts to your own ntfy topic:

```sh
export NTFY_TOPIC='your-private-topic'
python3 ttb_seat_monitor.py \
  --course-code ABC123H1 \
  --course-title ABC123 \
  --section LEC0101 \
  --session 20269 \
  --division ARTSC \
  --watch --interval 30
```

The default is one API check. Watch mode stops with Ctrl+C. The minimum polling interval is 30 seconds. Keep your ntfy topic private because anyone who knows it may be able to send notifications to it.

## Status values

- `OPEN`: current enrolment is below the section capacity
- `FULL`: current enrolment has reached capacity
- `CANCELLED`: the API marks the section as cancelled
- `MISSING`: the course or section was not found in the response

Verify any opening in ACORN and complete enrolment yourself. API data can lag behind ACORN.
