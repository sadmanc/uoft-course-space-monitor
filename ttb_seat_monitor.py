#!/usr/bin/env python3
"""Check a University of Toronto Timetable Builder section for space."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

API_URL = "https://api.easi.utoronto.ca/ttb/getPageableCourses"


@dataclass(frozen=True)
class SeatStatus:
    state: str
    course: str
    section: str
    enrolled: int = 0
    capacity: int = 0
    waitlist: int = 0
    waitlistable: bool = False

    def summary(self) -> str:
        if self.state == "OPEN":
            return (f"OPEN {self.course} {self.section}: "
                    f"{self.capacity - self.enrolled} seat(s) available; "
                    f"{self.enrolled}/{self.capacity} enrolled; "
                    f"waitlist {self.waitlist} ({'open' if self.waitlistable else 'closed'})")
        return f"{self.state} {self.course} {self.section}"


def request_body(args: argparse.Namespace) -> bytes:
    body = {
        "courseCodeAndTitleProps": {
            "courseCode": "",
            "courseTitle": args.course_title,
            "courseSectionCode": "",
            "searchCourseDescription": True,
        },
        "departmentProps": [],
        "campuses": [],
        "sessions": [args.session],
        "requirementProps": [],
        "instructor": "",
        "courseLevels": [],
        "deliveryModes": [],
        "dayPreferences": [],
        "timePreferences": [],
        "divisions": [args.division],
        "creditWeights": [],
        "availableSpace": False,
        "waitListable": False,
        "page": 1,
        "pageSize": 50,
        "direction": "asc",
    }
    return json.dumps(body).encode("utf-8")


def fetch_status(args: argparse.Namespace) -> SeatStatus:
    request = Request(
        API_URL,
        data=request_body(args),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=args.timeout) as response:
        data = json.loads(response.read())

    payload = data.get("payload") or {}
    courses = (payload.get("pageableCourse") or {}).get("courses") or []
    for course in courses:
        if course.get("code") != args.course_code:
            continue
        for section in course.get("sections") or []:
            if section.get("name") != args.section:
                continue
            if section.get("cancelInd") == "Y":
                return SeatStatus("CANCELLED", args.course_code, args.section)
            enrolled = int(section.get("currentEnrolment", 0))
            capacity = int(section.get("maxEnrolment", 0))
            waitlist = int(section.get("currentWaitlist", 0))
            waitlistable = section.get("waitlistInd") == "Y"
            state = "OPEN" if enrolled < capacity else "FULL"
            return SeatStatus(state, args.course_code, args.section, enrolled,
                              capacity, waitlist, waitlistable)
    return SeatStatus("MISSING", args.course_code, args.section)


def notify(topic: str, title: str, message: str, timeout: int) -> None:
    url = f"https://ntfy.sh/{quote(topic, safe='')}"
    request = Request(url, data=message.encode("utf-8"), headers={"Title": title})
    with urlopen(request, timeout=timeout) as response:
        if response.status >= 300:
            raise RuntimeError(f"notification service returned HTTP {response.status}")


def check(args: argparse.Namespace, previous: SeatStatus | None) -> SeatStatus:
    status = fetch_status(args)
    print(time.strftime("%Y-%m-%d %H:%M:%S %Z"), status.summary(), flush=True)

    topic = args.ntfy_topic
    if not topic:
        return status

    title_prefix = f"{args.course_code} {args.section}"
    if status.state == "OPEN" and (previous is None or previous.state != "OPEN"):
        notify(topic, f"Seat open: {title_prefix}", status.summary(), args.timeout)
    elif status.state == "FULL" and previous is not None and previous.state == "OPEN":
        notify(topic, f"Seat filled: {title_prefix}", status.summary(), args.timeout)

    if status.waitlistable and not (previous and previous.waitlistable):
        notify(topic, f"Waitlist open: {title_prefix}", status.summary(), args.timeout)
    elif previous and status.waitlist < previous.waitlist:
        notify(topic, f"Waitlist moved: {title_prefix}", status.summary(), args.timeout)

    if status.state in {"MISSING", "CANCELLED"}:
        notify(topic, f"Check course listing: {title_prefix}", status.summary(), args.timeout)
    return status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-code", required=True, help="Full course code from the API, such as ABC123H1")
    parser.add_argument("--course-title", required=True, help="Course title/code used in Timetable Builder search")
    parser.add_argument("--section", required=True, help="Section name, such as LEC0101")
    parser.add_argument("--session", required=True, help="Timetable Builder session code, such as 20269")
    parser.add_argument("--division", required=True, help="Division code used by Timetable Builder")
    parser.add_argument("--watch", action="store_true", help="Continue polling until stopped with Ctrl+C")
    parser.add_argument("--interval", type=int, default=30, help="Seconds between checks in watch mode (minimum 30)")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP request timeout in seconds")
    parser.add_argument("--ntfy-topic", default=os.environ.get("NTFY_TOPIC", ""),
                        help="Optional private ntfy.sh topic; prefer the NTFY_TOPIC environment variable")
    args = parser.parse_args()
    if args.interval < 30:
        parser.error("--interval must be at least 30 seconds")
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    return args


def main() -> int:
    args = parse_args()
    previous: SeatStatus | None = None
    failures = 0
    while True:
        try:
            previous = check(args, previous)
            failures = 0
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError, TypeError, OSError) as error:
            failures += 1
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S %Z')} ERROR {type(error).__name__}: {error}",
                  file=sys.stderr, flush=True)
            if not args.watch:
                return 1
        if not args.watch:
            return 0
        delay = args.interval if not failures else min(args.interval * (2 ** min(failures, 4)), 300)
        try:
            time.sleep(delay)
        except KeyboardInterrupt:
            print("Stopped.")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
