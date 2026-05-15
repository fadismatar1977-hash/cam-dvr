import cv2
import numpy as np
import os
import urllib.request


class AIEnhancer:
    def __init__(self, enable_super_res=False):
        self.enable_super_res = enable_super_res
        self.sr_model = None
        self.use_ai = True

        self._download_models()

    def _download_models(self):
        if not self.enable_super_res:
            return

        model_dir = os.path.join(os.path.dirname(__file__), "models")
        os.makedirs(model_dir, exist_ok=True)
        model_path = os.path.join(model_dir, "ESPCN_x2.pb")

        if not os.path.exists(model_path):
            try:
                url = "https://github.com/fannymonori/TF-ESPCN/raw/master/export/ESPCN_x2.pb"
                urllib.request.urlretrieve(url, model_path)
                self.sr_model = cv2.dnn_superres.DnnSuperResImpl_create()
                self.sr_model.readModel(model_path)
                self.sr_model.setModel("espcn", 2)
            except Exception:
                self.sr_model = None

    def enhance(self, frame: np.ndarray) -> np.ndarray:
        if not self.use_ai or frame is None:
            return frame

        try:
            h, w = frame.shape[:2]
            if h < 100 or w < 100:
                return frame

            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
            l = clahe.apply(l)
            enhanced = cv2.merge([l, a, b])
            enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

            sharpen = np.array([[-1, -1, -1],
                                [-1,  9, -1],
                                [-1, -1, -1]])
            enhanced = cv2.filter2D(enhanced, -1, sharpen)

            enhanced = cv2.fastNlMeansDenoisingColored(enhanced, None, 6, 6, 7, 21)

            if self.sr_model and self.enable_super_res and h < 480 and w < 640:
                try:
                    enhanced = self.sr_model.upsample(enhanced)
                except Exception:
                    pass

            return enhanced

        except Exception:
            return frame


class AIMotionDetector:
    def __init__(self, sensitivity=5000):
        self.sensitivity = sensitivity
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=36, detectShadows=True
        )
        self.min_area = 500

    def detect(self, frame: np.ndarray) -> tuple[bool, float, np.ndarray]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        fg_mask = self.bg_subtractor.apply(gray)
        _, thresh = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)
        thresh = cv2.dilate(thresh, None, iterations=3)
        thresh = cv2.erode(thresh, None, iterations=1)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        total_motion = 0
        valid_motion_count = 0

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.min_area:
                continue
            x, y, bw, bh = cv2.boundingRect(cnt)
            aspect = bw / max(bh, 1)
            if aspect < 0.3 or aspect > 5.0:
                continue
            total_motion += area
            valid_motion_count += 1

        motion = total_motion > self.sensitivity and valid_motion_count > 0

        if motion and valid_motion_count > 0:
            cv2.putText(frame, f"Motion: {valid_motion_count}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        return motion, total_motion, frame
