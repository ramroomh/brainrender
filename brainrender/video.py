from pathlib import Path
from rich.progress import track
from rich import print
from pyinspect._colors import orange
import os
import numpy as np

from brainrender.camera import check_camera_param, get_camera_params
from brainrender._video import Video
import brainrender as br


class VideoMaker:
    def __init__(self, scene, save_fld, name, fmt="mp4", make_frame_func=None):
        """
            Creates a video by animating a scene and saving a sequence
            of screenshots.

            :param scene: the instance of Scene to be animated
            :param save_fld: str, Path. Where the video will be savd
            :param save_name: str, name of the video
            :param fmt: str. Video format (e.g. 'mp4')
            :param make_frame_func: None, optional. If passed it should be a
                function that takes the Scene to be animated as the fist argument abd
                the current frame number as second. At every frame this function
                can do what's needed to animate the scene
        """
        self.scene = scene

        self.save_fld = Path(save_fld)
        self.save_fld.mkdir(exist_ok=True)
        self.save_name = name
        self.video_format = fmt

        self.make_frame_func = make_frame_func or self._make_frame

    @staticmethod
    def _make_frame(
        scene, frame_number, tot_frames, azimuth=0, elevation=0, roll=0
    ):
        """
            Default `make_frame_func`. Rotaets the camera in 3 directions

            :param scene: scene to be animated.
            :param frame_number: int, not used
            :param tot_frames: int, total numner of frames
            :param azimuth: integer, specify the rotation in degrees 
                        per frame on the relative axis. (Default value = 0)
            :param elevation: integer, specify the rotation in degrees 
                        per frame on the relative axis. (Default value = 0)
            :param roll: integer, specify the rotation in degrees 
                        per frame on the relative axis. (Default value = 0)
        """
        scene.plotter.show(interactive=False)
        scene.plotter.camera.Elevation(elevation)
        scene.plotter.camera.Azimuth(azimuth)
        scene.plotter.camera.Roll(roll)

    def generate_frames(self, fps, duration, video, *args, **kwargs):
        """
            Loop to generate frames

            :param fps: int, frame rate
            :param duration: float, video duration in seconds
            :param video: vedo Video class used to create the video
        """
        nframes = int(fps * duration)
        for i in track(range(nframes), description="Generating frames"):
            self.make_frame_func(self.scene, i, nframes, *args, **kwargs)
            video.addFrame()

    def make_video(
        self, *args, duration=10, fps=30, render_kwargs={}, **kwargs
    ):
        """
        Creates a video using user defined parameters

        :param *args: any extra argument to be bassed to `make_frame_func`
        :param duration: float, duratino of the video in seconds
        :param fps: int, frame rate
        :param **kwargs: any extra keyword argument to be bassed to `make_frame_func`
        """
        _off = br.settings.OFFSCREEN
        br.settings.OFFSCREEN = True  # render offscreen

        self.scene.render(interactive=False, **render_kwargs)

        # cd to folder where the video will be saved
        curdir = os.getcwd()
        os.chdir(self.save_fld)
        print(f"Saving video in {self.save_fld}")

        # Create video
        video = Video(
            name=self.save_name,
            duration=duration,
            fps=fps,
            fmt=self.video_format,
        )

        # Make frames
        self.generate_frames(fps, duration, video, *args, **kwargs)

        self.scene.close()
        video.close()  # merge all the recorded frames
        br.settings.OFFSCREEN = _off

        # Cd back to original dir
        os.chdir(curdir)

        return os.path.join(
            self.save_fld, self.save_name + "." + self.video_format
        )


def sigma(x):
    """
        Sigmoid curve
    """
    y = 1.05 / (1 + np.exp(-8 * (x - 0.5))) - 0.025
    if y < 0:
        y = 0
    if y > 1:
        y = 1
    return y


class Animation(VideoMaker):
    """
        The animation class facilitates the creation of videos
        by specifying a series of keyframes at given moments during
        the video. At each keyframe various parameters (e.g. camera position)
        is specified and the video is created by interpolating
        between consecutive key frames.
    """

    _last_frame_params = None

    def __init__(self, scene, save_fld, name, fmt="mp4"):
        """
            The animation class facilitates the creation of videos
            by specifying a series of keyframes at given moments during
            the video. At each keyframe various parameters (e.g. camera position)
            is specified and the video is created by interpolating
            between consecutive key frames.

            :param scene: the instance of Scene to be animated
            :param save_fld: str, Path. Where the video will be savd
            :param save_name: str, name of the video
            :param fmt: str. Video format (e.g. 'mp4')
        """
        VideoMaker.__init__(self, scene, save_fld, name, fmt=fmt)

        self.keyframes = {}
        self.keyframes[0] = dict(  # make sure first frame is a keyframe
            zoom=None, camera=None, callback=None
        )

    def add_keyframe(
        self,
        time,
        duration=0,
        zoom=None,
        camera=None,
        interpol="sigma",
        callback=None,
    ):
        """
            Add a keyframe to the video.

            :param time: float, time in seconds during the video
                at which the keyframe takes place.
            :param duration: float, if >0 the key frame is repeated
                every 5ms to go from start to start+duration
            :param zoom: camera zoom
            :param camera: dictionary of camera parameters
            :param interpol: str, if `sigma` or `linear` specifies
                the interpolation mode between key frames.
            :param callback: function which takes scene, current video
                frame and total number of frames in video as arguments.
                can be used to make stuff happen during a key frame (e.g. remove
                an actor)
        """
        if camera is not None:
            camera = check_camera_param(camera)

        if time in self.keyframes.keys() and time > 0:
            print(f"[b {orange}]Keyframe {time} already exists, overwriting!")

        if not duration:
            self.keyframes[time] = dict(
                zoom=zoom, camera=camera, callback=callback, interpol=interpol,
            )
        else:
            for time in np.arange(time, time + duration, 0.001):
                self.keyframes[time] = dict(
                    zoom=zoom,
                    camera=camera,
                    callback=callback,
                    interpol=interpol,
                )

    def get_keyframe_framenumber(self, fps):
        """
            Keyframes are defines in units of time (s), so we need
            to know to which frame each keyframe corresponds

            :param fps: int, frame rate
        """
        self.keyframes = {
            int(np.floor(s * fps)): v for s, v in self.keyframes.items()
        }
        self.keyframes_numbers = sorted(list(self.keyframes.keys()))

    def generate_frames(self, fps, duration, video):
        """
            Loop to generate frames

            :param fps: int, frame rate
            :param duration: float, video duration in seconds
            :param video: vedo Video class used to create the video
        """
        self.get_keyframe_framenumber(fps)

        self.nframes = int(fps * duration)
        self.last_keyframe = max(self.keyframes_numbers)

        if self.last_keyframe > self.nframes:
            print(
                f"[b {orange}]The video will be {self.nframes} frames long, but you have defined keyframes after that, try increasing video duration?"
            )

        for framen in track(
            range(self.nframes), description="Generating frames..."
        ):
            self._make_frame(framen)
            video.addFrame()

    def get_frame_params(self, frame_number):
        """
            Get current parameters (e.g. camera position)
            based on frame numbe and defined key frames.

            If frame number is a keyframe or is after a keyframe
            then the params are those of that/the last keyframe.
            Else the params of two consecutive keyframes are interpolate
            using either a linear or sigmoid function.
        """
        if frame_number in self.keyframes_numbers:
            # Check if current frame is a key frame
            params = self.keyframes[frame_number]

        elif frame_number > self.last_keyframe:
            # check if current frame is past the last keyframe
            params = self.keyframes[self.last_keyframe]
            params["callback"] = None

        else:
            # interpolate between two key frames
            prev = [n for n in self.keyframes_numbers if n < frame_number][-1]
            nxt = [n for n in self.keyframes_numbers if n > frame_number][0]
            kf1, kf2 = self.keyframes[prev], self.keyframes[nxt]

            self.segment_fact = (nxt - frame_number) / (nxt - prev)
            if kf2["interpol"] == "sigma":
                self.segment_fact = sigma(self.segment_fact)

            params = dict(
                camera=self._interpolate_cameras(kf1["camera"], kf2["camera"]),
                zoom=self._interpolate_values(kf1["zoom"], kf2["zoom"]),
                callback=None,
            )

        # get current camera (to avoid using scene's default)
        if params["camera"] is None:
            params["camera"] = get_camera_params(self.scene)
        return params

    def _make_frame(self, frame_number):
        """
            Creates a frame with the correct params
            and calls the keyframe callback function if defined.

            :param frame_number: int, current frame number
        """
        frame_params = self.get_frame_params(frame_number)

        # callback
        if frame_params["callback"] is not None:
            frame_params["callback"](self.scene, frame_number, self.nframes)

        # render
        self.scene.render(
            camera=frame_params["camera"],
            zoom=frame_params["zoom"],
            interactive=False,
        )

    def _interpolate_cameras(self, cam1, cam2):
        """
            Interpolate the parameters of two cameras
        """
        if cam1 is None:
            return cam2
        elif cam2 is None:
            return cam1

        interpolated = {}
        for (k, v1), (k2, v2) in zip(cam1.items(), cam2.items()):
            if k != k2:
                raise ValueError(f"Keys mismatch: {k} - {k2}")
            interpolated[k] = self._interpolate_values(v1, v2)
        return interpolated

    def _interpolate_values(self, v1, v2):
        """
            Interpolate two valuess
        """
        if v1 is None:
            return v2
        elif v2 is None:
            return v1

        return self.segment_fact * np.array(v1) + (
            1 - self.segment_fact
        ) * np.array(v2)
