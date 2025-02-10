from collections import deque
from datetime import datetime
from logging import Logger
from typing import Any, Dict, Tuple

import cv2
import numpy as np

from argussight.core.video_processes.streamer.streamer import Streamer


class Point:
    def __init__(self, position: Tuple[int, int], creation_time: datetime) -> None:
        self._starting_position = np.array(position).reshape(1, 2)
        self._current_position = np.array(position).reshape(1, 2)
        self._creation_time = creation_time

    def update_position(self, new_position: Tuple[int, int]) -> None:
        self._current_position = np.array(new_position).reshape(1, 2)

    # calculate the average speed it took the point to travel from starting point to current position
    def calculate_speed(self, current_time: datetime, direction: int = 1) -> float:
        elapsed_time = (current_time - self._creation_time).total_seconds()
        if elapsed_time > 0:
            traveled_distance = (
                self._current_position[0, direction]
                - self._starting_position[0, direction]
            )
            return traveled_distance / elapsed_time
        return 0.0


class FlowDetection(Streamer):
    def __init__(
        self,
        collector_config,
        free_port,
        exposed_parameters: Dict[str, Any],
        logger: Logger,
    ) -> None:
        super().__init__(collector_config, free_port, exposed_parameters, logger)
        self._previous_frame = None
        self._min_distance = 50
        self._p0 = []
        self._speeds = deque(maxlen=20)

        self._time_stamp_used = True  # this process needs the current time_stamps for calculation the flow speed
        self._command_timeout = 0.04  # this process needs to handle incoming frames consecutavely hence low waiting time

    def is_point_in_roi(self, x: int, y: int) -> bool:
        rx, ry, rw, rh = self._parameters["roi"]
        return rx <= x <= rx + rw and ry <= y <= ry + rh

    def remove_outliers(self) -> None:
        if self._p0 is not None:
            result = [
                point
                for point in self._p0
                if self.is_point_in_roi(*(point._current_position)[0])
            ]
            self._p0 = result if len(result) > 0 else []

    def detect_new_features(self, gray_frame, time_stamp: datetime) -> None:
        x, y, w, h = self._parameters["roi"]
        roi_gray = gray_frame[y : y + h, x : x + w]

        if len(self._p0) > 0:
            # Select new points if old ones moved out of frame
            new_points = cv2.goodFeaturesToTrack(
                roi_gray, mask=None, **self._parameters["feature_params"]
            )

            if new_points is not None:
                # Filter new points based on the minimum distance
                current_points = np.array(
                    [pt._current_position for pt in self._p0], dtype=np.float32
                ).reshape(-1, 1, 2)
                new_points += np.array([x, y])
                for new_point in new_points:
                    new_point = new_point.reshape(-1, 2)
                    distances = np.sqrt(((current_points - new_point) ** 2).sum(axis=2))
                    if np.min(distances) > self._min_distance:
                        self._p0.append(
                            Point([new_point[0][0], new_point[0][1]], time_stamp)
                        )
                        current_points = np.append(
                            current_points, new_point.reshape(1, 1, 2), axis=0
                        )
        else:
            points = cv2.goodFeaturesToTrack(
                roi_gray, mask=None, **self._parameters["feature_params"]
            )
            if points is not None:
                for pt in points:
                    absolute_position = [pt[0][0] + x, pt[0][1] + y]
                    self._p0.append(Point(absolute_position, time_stamp))

    def calculate_average_speed(self, time_stamp: datetime) -> int:
        current_frame_average_speed = np.mean(
            np.array(
                [point.calculate_speed(time_stamp, direction=1) for point in self._p0]
            )
        )
        self._speeds.append(current_frame_average_speed)
        return int(sum(self._speeds) / len(self._speeds))

    def detect_and_track_features(self, frame, time_stamp: datetime) -> None:
        x, y, w, h = self._parameters["roi"]

        if self._previous_frame is None:
            self._previous_frame = frame.copy()
            gray_previous_frame = cv2.cvtColor(self._previous_frame, cv2.COLOR_BGR2GRAY)

            self.detect_new_features(gray_previous_frame, time_stamp)
        else:
            gray_previous_frame = cv2.cvtColor(self._previous_frame, cv2.COLOR_BGR2GRAY)

        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if len(self._p0) > 0:
            # Calculate optical flow
            prev_points = np.array(
                [pt._current_position for pt in self._p0], dtype=np.float32
            ).reshape(-1, 1, 2)
            lk_params = self._parameters["lk_params"]
            lk_params["criteria"] = tuple(lk_params["criteria"])
            p1, st, err = cv2.calcOpticalFlowPyrLK(
                gray_previous_frame, gray_frame, prev_points, None, **lk_params
            )

            # Check if points were found
            if p1 is not None:
                # Select good points
                good_new = p1[st == 1]
                good_points = [
                    point for point, status in zip(self._p0, st) if status == 1
                ]

                # Update points and draw circles
                for point, new_position in zip(good_points, good_new):
                    new_position = new_position.ravel()
                    point.update_position(new_position)
                    frame = cv2.circle(
                        frame,
                        (int(new_position[0]), int(new_position[1])),
                        8,
                        (0, 255, 0),
                        2,
                    )

                # Update the previous frame, p0 and the speed
                self._previous_frame = frame.copy()
                self._p0 = good_points
                average_speed = self.calculate_average_speed(time_stamp)
                frame = cv2.putText(
                    frame,
                    f"average speed: {int(average_speed)} pixel/s",
                    (x + w + 50, int(y + h / 2)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                )

            if len(self._p0) <= 5:
                self.detect_new_features(gray_frame, time_stamp)

        else:
            self._previous_frame = None

        # Draw ROI
        frame = cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)

        self.remove_outliers()

        return frame

    def process_frame(self) -> None:
        self._processed_frame = self.detect_and_track_features(
            self._current_frame, self._current_frame_time
        )

    def prepare_setting_change(self, key: str) -> None:
        match key:
            case "roi":
                self._previous_frame = None
                self._processed_frame = None
                self._speeds = deque(maxlen=20)
                self._p0 = []
            case _:
                pass
