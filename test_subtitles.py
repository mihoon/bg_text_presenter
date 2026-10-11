# -*- coding: utf-8 -*-
"""자막(.srt/.smi) 읽기 테스트 - python test_subtitles.py"""
import os
import sys
import tempfile

import subtitles as st

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"   OK   {label}")
    else:
        print(f"   실패 {label}  {detail}")
        FAILURES.append(label)


SRT = """1
00:00:01,000 --> 00:00:03,500
<i>태초에 하나님이</i>
천지를 창조하시니라

2
00:00:04,000 --> 00:00:06,000
{\\an8}땅이 혼돈하고

3
00:01:02.5 --> 00:01:04.25
Ang Dios &amp; ang Pulong
"""

SMI = """<SAMI>
<HEAD><STYLE TYPE="text/css"><!--
.KRCC { Name:한국어; lang:ko-KR; }
.ENCC { Name:English; lang:en-US; }
--></STYLE></HEAD>
<BODY>
<SYNC Start=1000><P Class=ENCC>In the beginning
<SYNC Start=1000><P Class=KRCC>태초에<br>하나님이
<SYNC Start=3000><P Class=KRCC>&nbsp;
<SYNC Start=4000><P Class=KRCC>땅이 혼돈하고
<SYNC Start="7000"><P Class=KRCC>흑암이
</BODY></SAMI>
"""


def main():
    tmp = tempfile.mkdtemp()

    print("1) SRT")
    cues = st.parse_srt(SRT)
    check("자막 3개", len(cues) == 3, str(cues))
    check("시작/끝 시각", (cues[0].start, cues[0].end) == (1000, 3500), str(cues[0]))
    check("태그 제거 + 줄바꿈 유지", cues[0].text == "태초에 하나님이\n천지를 창조하시니라", repr(cues[0].text))
    check("ASS 위치 태그 제거", cues[1].text == "땅이 혼돈하고", repr(cues[1].text))
    check("점(.)과 짧은 밀리초", (cues[2].start, cues[2].end) == (62500, 64250), str(cues[2]))
    check("HTML 엔티티 해석", cues[2].text == "Ang Dios & ang Pulong", repr(cues[2].text))
    track = st.SubtitleTrack(cues)
    check("시작 전에는 없음", track.text_at(500) == "")
    check("구간 안", track.text_at(2000).startswith("태초에"))
    check("구간 끝(3.5초)에는 사라짐", track.text_at(3500) == "")
    check("다음 자막", track.text_at(5999) == "땅이 혼돈하고")

    print("\n2) SMI (한국어 + 영어)")
    cues = st.parse_smi(SMI)
    texts = [c.text for c in cues]
    check("한국어만 고름", texts == ["태초에\n하나님이", "땅이 혼돈하고", "흑암이"], str(texts))
    check("&nbsp; 에서 끝남", (cues[0].start, cues[0].end) == (1000, 3000), str(cues[0]))
    check("다음 SYNC 까지", (cues[1].start, cues[1].end) == (4000, 7000), str(cues[1]))
    check("마지막 자막은 5초", cues[2].end == 12000, str(cues[2]))

    print("\n3) 파일 인코딩과 자동 찾기")
    video = os.path.join(tmp, "주일설교.mp4")
    open(video, "wb").close()
    smi_path = os.path.join(tmp, "주일설교.smi")
    with open(smi_path, "wb") as f:
        f.write(SMI.encode("cp949"))
    check("같은 이름 .smi 찾기", st.find_subtitle_for(video) == smi_path, st.find_subtitle_for(video))
    track = st.load_subtitle(smi_path)
    check("CP949 로 저장된 SMI 읽기", track is not None and track.text_at(1500) == "태초에\n하나님이",
          repr(track.text_at(1500) if track else None))

    srt_path = os.path.join(tmp, "주일설교.SRT")
    with open(srt_path, "wb") as f:
        f.write(b"\xef\xbb\xbf" + SRT.encode("utf-8"))
    check("둘 다 있으면 .srt 우선 (대소문자 무관)", st.find_subtitle_for(video) == srt_path,
          st.find_subtitle_for(video))
    track = st.load_subtitle(srt_path)
    check("UTF-8 BOM SRT 읽기", track is not None and len(track) == 3)

    other = os.path.join(tmp, "광고.mp4")
    open(other, "wb").close()
    tagged = os.path.join(tmp, "광고.ko.srt")
    with open(tagged, "w", encoding="utf-8") as f:
        f.write(SRT)
    open(os.path.join(tmp, "광고.en.srt"), "w").close()
    check("언어 표시가 붙은 한국어 자막", st.find_subtitle_for(other) == tagged, st.find_subtitle_for(other))

    lonely = os.path.join(tmp, "자막없음.mp4")
    open(lonely, "wb").close()
    check("없으면 빈 문자열", st.find_subtitle_for(lonely) == "")
    empty = os.path.join(tmp, "빈자막.srt")
    open(empty, "w").close()
    check("빈 파일은 None", st.load_subtitle(empty) is None)

    utf16 = os.path.join(tmp, "utf16.srt")
    with open(utf16, "wb") as f:
        f.write(SRT.encode("utf-16"))
    track = st.load_subtitle(utf16)
    check("UTF-16 SRT 읽기", track is not None and track.text_at(5000) == "땅이 혼돈하고")

    print()
    if FAILURES:
        print(f"실패 {len(FAILURES)}건: {FAILURES}")
        return 1
    print("전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
