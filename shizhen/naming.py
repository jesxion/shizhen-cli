"""文件命名，规则与小程序 shareFileName 一致，并避免覆盖同名文件。"""
import os
import re

TITLE_MAX = 30
_HASHTAG = re.compile(r"#\S+")
_ILLEGAL = re.compile(r'[\/:*?"<>|\x00-\x1f\x7f]')
_SPACES = re.compile(r"\s+")


def clean_title(title):
    text = _HASHTAG.sub(" ", title or "")
    text = _ILLEGAL.sub(" ", text)
    text = _SPACES.sub(" ", text).strip()
    return text[:TITLE_MAX].strip()


def file_name(title, kind, ext):
    """视频为 标题.ext，音频为 标题-音频.ext。ext 含点。"""
    base = clean_title(title) or "拾帧"
    if kind == "audio":
        base += "-音频"
    return base + ext


def unique_path(directory, name):
    """同名不覆盖：依次尝试 名称 (2).ext、名称 (3).ext。"""
    stem, ext = os.path.splitext(name)
    candidate = os.path.join(directory, name)
    index = 2
    while os.path.exists(candidate) or os.path.exists(candidate + ".part"):
        candidate = os.path.join(directory, "%s (%d)%s" % (stem, index, ext))
        index += 1
    return candidate
