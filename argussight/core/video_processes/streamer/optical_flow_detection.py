from datetime import datetime
from logging import Logger
from typing import Any, Dict

import cv2
import numpy as np

from argussight.core.video_processes.streamer.streamer import Streamer


class OpticalFlowDetection(Streamer):
    def __init__(
        self,
        collector_config,
        free_port,
        exposed_parameters: Dict[str, Any],
        logger: Logger,
    ) -> None:
        super().__init__(collector_config, free_port, exposed_parameters, logger)
        self._previous_frame = None
        self._speeds = []
        self._current_speed = 0
        self._back_sub = cv2.createBackgroundSubtractorMOG2(
            history=50, varThreshold=10, detectShadows=True
        )

        self._time_stamp_used = True
        self._command_timeout = 0.02

    def update_speed_value(self) -> None:
        if not self._speeds:
            self._current_speed = 0
        self._current_speed = sum(self._speeds) / len(self._speeds)
        self._speeds.clear()

    def get_background_percentage(self, frame):
        # Calculate the percentage of background in roi
        mask = self._back_sub.apply(frame)
        x, y, w, h = self._parameters["roi"]
        mask_roi = mask[y : y + h, x : x + w]
        non_background_pixels = np.count_nonzero(mask_roi)
        total_pixels = mask_roi.size
        background_percentage = 100 - (non_background_pixels / total_pixels * 100)

        return background_percentage, mask_roi

    def calculate_flow(self, frame, time_stamp: datetime):
        x, y, w, h = self._parameters["roi"]

        if self._previous_frame is None:
            self._previous_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            self._last_speed_update = time_stamp
            self._last_time_stamp = time_stamp
            return self._previous_frame

        next_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Extract the ROI from the current and previous frame
        prvs_frame_roi = self._previous_frame[y : y + h, x : x + w]
        next_frame_roi = next_frame[y : y + h, x : x + w]

        # Update previous_frame for next iteration
        self._previous_frame = next_frame

        bg_percentage, bg_mask = self.get_background_percentage(frame)
        if 95 < bg_percentage:
            cv2.putText(
                frame,
                "Could not detect flow",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )
            cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)

            return frame

        # Calculate optical flow within the ROI
        flow = cv2.calcOpticalFlowFarneback(
            prvs_frame_roi, next_frame_roi, None, **self._parameters["flow_params"]
        )
        # We do not want to consider the flow of the background
        binary_mask = binary_mask = (bg_mask > 0).astype(np.uint8)
        flow = flow * binary_mask[..., None]

        # Calculate and update speed
        flow_y = flow[..., 1]
        y_speed_per_second = (
            np.mean(np.abs(flow_y)[flow_y != 0])
            / (time_stamp - self._last_time_stamp).total_seconds()
        )
        self._last_time_stamp = time_stamp
        self._speeds.append(y_speed_per_second)

        if (time_stamp - self._last_speed_update).total_seconds() > 1:
            self.update_speed_value()
            self._last_speed_update = time_stamp

        # Visualize the optical flow within the ROI
        hsv_roi = np.zeros_like(frame[y : y + h, x : x + w])
        hsv_roi[..., 1] = 255
        mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        hsv_roi[..., 0] = ang * 180 / np.pi / 2
        hsv_roi[..., 2] = cv2.normalize(mag, None, 0, 255, cv2.NORM_MINMAX)
        bgr_roi = cv2.cvtColor(hsv_roi, cv2.COLOR_HSV2BGR)

        # Overlay the ROI visualization and Speed-value on the original frame
        frame[y : y + h, x : x + w] = cv2.addWeighted(
            frame[y : y + h, x : x + w], 0.5, bgr_roi, 0.5, 0
        )
        cv2.putText(
            frame,
            f"Y Speed: {self._current_speed:.2f} pixels/second",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

        cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)

        return frame

    def process_frame(self) -> None:
        self._processed_frame = self.calculate_flow(
            self._current_frame, self._current_frame_time
        )

    def prepare_setting_change(self, key: str) -> None:
        match key:
            case "roi":
                self._previous_frame = None
                self._processed_frame = None
                self._speeds.clear()
            case _:
                pass
