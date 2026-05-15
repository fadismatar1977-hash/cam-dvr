import cv2
import numpy as np
import os
import time
import urllib.request


class AIEnhancer:
    def __init__(self, config=None):
        self.config = config or {}
        self.use_ai = True
        self.enable_super_res = self.config.get("ai_super_res", False)
        self.quality = self.config.get("ai_quality", 1)
        self.process_width = self.config.get("process_width", 640)
        self.frame_skip = self.config.get("frame_skip", 1)
        self.sr_model = None
        self._frame_count = 0
        self._last_enhanced = None

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

    def _analyze_frame(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean = np.mean(gray)
        std = np.std(gray)
        return mean, std

    def _auto_contrast(self, frame, clip=2):
        channels = cv2.split(frame)
        out = []
        for ch in channels:
            lo, hi = np.percentile(ch, [clip, 100 - clip])
            if hi - lo < 1:
                out.append(ch)
                continue
            scaled = np.clip((ch.astype(np.float32) - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)
            out.append(scaled)
        return cv2.merge(out)

    def _unsharp_mask(self, frame, sigma=1.0, strength=1.5):
        blurred = cv2.GaussianBlur(frame, (0, 0), sigma)
        return cv2.addWeighted(frame, 1.0 + strength, blurred, -strength, 0)

    def enhance(self, frame):
        if not self.use_ai or frame is None:
            return frame
        try:
            h, w = frame.shape[:2]
            if h < 50 or w < 50:
                return frame

            self._frame_count += 1
            do_process = (self._frame_count % self.frame_skip == 0)

            if not do_process and self._last_enhanced is not None:
                return cv2.resize(self._last_enhanced, (w, h))

            scale = min(1.0, self.process_width / max(w, 1))
            h_small = max(1, int(h * scale))
            w_small = max(1, int(w * scale))
            small = cv2.resize(frame, (w_small, h_small))

            mean_bright, noise = self._analyze_frame(small)

            small = self._auto_contrast(small, clip=2)

            lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)

            clip_limit = 3.0 if mean_bright < 80 else 2.0
            if mean_bright < 50:
                clip_limit = 4.0
            clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
            l = clahe.apply(l)

            if mean_bright < 70:
                gamma = 0.7 + (70 - mean_bright) / 200
                gamma = max(0.5, min(1.0, gamma))
                inv_gamma = 1.0 / gamma
                table = np.array([(i / 255.0) ** inv_gamma * 255 for i in range(256)]).astype(np.uint8)
                l = cv2.LUT(l, table)

            enhanced = cv2.merge([l, a, b])
            enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

            if self.quality >= 1:
                enhanced = self._unsharp_mask(enhanced, sigma=1.0, strength=1.2)

            if self.quality >= 2:
                d = 5
                sigma_color = 30
                sigma_space = 30
                enhanced = cv2.bilateralFilter(enhanced, d, sigma_color, sigma_space)

            if self.quality >= 3:
                enhanced = cv2.addWeighted(
                    enhanced, 1.0,
                    cv2.GaussianBlur(enhanced, (0, 0), 3),
                    -0.3, 0
                )

            if self.sr_model and self.enable_super_res and h < 480 and w < 640:
                try:
                    enhanced = self.sr_model.upsample(enhanced)
                    small = cv2.resize(frame, (enhanced.shape[1], enhanced.shape[0]))
                except Exception:
                    pass

            if scale < 1.0:
                enhanced = cv2.resize(enhanced, (w, h))

            self._last_enhanced = enhanced
            return enhanced

        except Exception:
            return frame


class AIMotionDetector:
    def __init__(self, sensitivity=5000):
        self.sensitivity = sensitivity
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(
            history=300, varThreshold=32, detectShadows=True
        )
        self.min_area = 500
        self._frame_count = 0
        self._skip = 1

    def detect(self, frame):
        self._frame_count += 1
        if self._frame_count % self._skip != 0:
            return False, 0, frame

        h, w = frame.shape[:2]
        scale = min(1.0, 480 / max(h, w))
        if scale < 1.0:
            small = cv2.resize(frame, (int(w * scale), int(h * scale)))
        else:
            small = frame

        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        fg_mask = self.bg_subtractor.apply(gray)
        _, thresh = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)
        thresh = cv2.dilate(thresh, None, iterations=2)
        thresh = cv2.erode(thresh, None, iterations=1)

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        total_motion = 0
        valid_motion_count = 0

        for cnt in contours:
            area = cv2.contourArea(cnt) / (scale * scale)
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
