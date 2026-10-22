"""Vertical Manim scenes for the Raspberry Phone video.

The scenes mirror the visual language used in the MNIST video: black canvas,
white geometry, blue information flow, red only for delay/error, monospaced
type, and sparse labels. Render a lightweight preview with:

    MANIM_PIXEL_WIDTH=270 MANIM_PIXEL_HEIGHT=480 \
      .venv-manim/bin/manim -ql animations/phone_scenes.py PipelineOverview
"""

from __future__ import annotations

import math
import os

import numpy as np
from manim import (
    BLACK,
    DOWN,
    LEFT,
    ORIGIN,
    RIGHT,
    UP,
    AnimationGroup,
    Arc,
    Arrow,
    Circle,
    Create,
    DashedLine,
    Dot,
    FadeIn,
    FadeOut,
    GrowFromCenter,
    LaggedStart,
    Line,
    ManimColor,
    Rectangle,
    RoundedRectangle,
    Scene,
    ShowPassingFlash,
    Square,
    Succession,
    Text,
    Transform,
    TransformFromCopy,
    VGroup,
    VMobject,
    Write,
    config,
    linear,
)


config.background_color = BLACK
config.pixel_width = int(os.getenv("MANIM_PIXEL_WIDTH", "1080"))
config.pixel_height = int(os.getenv("MANIM_PIXEL_HEIGHT", "1920"))
config.frame_width = 9
config.frame_height = 16

WHITE = ManimColor("#F7F7F2")
GRAY = ManimColor("#777773")
DIM = ManimColor("#28282A")
BLUE = ManimColor("#58C4DD")
RED = ManimColor("#FC6255")
FONT = "Menlo"


def label(text: str, size: int = 32, color: ManimColor = WHITE, **kwargs) -> Text:
    return Text(text, font=FONT, font_size=size, color=color, **kwargs)


def card(width: float, height: float, color: ManimColor = WHITE) -> RoundedRectangle:
    return RoundedRectangle(
        corner_radius=0.18,
        width=width,
        height=height,
        stroke_color=color,
        stroke_width=2.2,
        fill_color=BLACK,
        fill_opacity=1,
    )


def waveform(width: float = 5.8, height: float = 1.35, samples: int = 70) -> VMobject:
    """Deterministic speech-like waveform centered at the origin."""

    xs = np.linspace(-width / 2, width / 2, samples)
    envelope = np.sin(np.linspace(0, math.pi, samples)) ** 0.65
    signal = (
        np.sin(np.linspace(0, 8 * math.pi, samples))
        + 0.45 * np.sin(np.linspace(0, 19 * math.pi, samples) + 0.6)
    )
    points = [
        [x, height * envelope[index] * signal[index] / 1.45, 0]
        for index, x in enumerate(xs)
    ]
    path = VMobject(stroke_color=WHITE, stroke_width=3)
    path.set_points_smoothly(points)
    return path


def microphone(scale: float = 1.0) -> VGroup:
    capsule = RoundedRectangle(
        corner_radius=0.32,
        width=0.82,
        height=1.55,
        stroke_color=WHITE,
        stroke_width=3,
    )
    cradle = Arc(radius=0.72, start_angle=math.pi, angle=math.pi, color=WHITE, stroke_width=3)
    cradle.shift(DOWN * 0.20)
    stem = Line([0, -0.90, 0], [0, -1.38, 0], color=WHITE, stroke_width=3)
    base = Line([-0.55, -1.38, 0], [0.55, -1.38, 0], color=WHITE, stroke_width=3)
    return VGroup(capsule, cradle, stem, base).scale(scale)


def speaker(scale: float = 1.0) -> VGroup:
    body = VGroup(
        Rectangle(width=0.62, height=0.88, stroke_color=WHITE, stroke_width=3),
        VMobject(stroke_color=WHITE, stroke_width=3).set_points_as_corners(
            [[0.31, 0.44, 0], [0.92, 0.94, 0], [0.92, -0.94, 0], [0.31, -0.44, 0]]
        ),
    )
    waves = VGroup(
        Arc(radius=0.60, start_angle=-0.72, angle=1.44, color=BLUE, stroke_width=3).shift(RIGHT * 0.84),
        Arc(radius=1.00, start_angle=-0.72, angle=1.44, color=BLUE, stroke_width=3).shift(RIGHT * 0.84),
    )
    return VGroup(body, waves).scale(scale)


def chip(scale: float = 1.0) -> VGroup:
    shell = RoundedRectangle(
        corner_radius=0.16,
        width=2.35,
        height=1.75,
        stroke_color=WHITE,
        stroke_width=3,
    )
    core = Square(side_length=0.70, stroke_color=BLUE, stroke_width=2)
    pins = VGroup()
    for x in np.linspace(-0.78, 0.78, 4):
        pins.add(Line([x, 0.88, 0], [x, 1.13, 0], color=WHITE, stroke_width=2))
        pins.add(Line([x, -0.88, 0], [x, -1.13, 0], color=WHITE, stroke_width=2))
    return VGroup(shell, core, pins).scale(scale)


def cloud(width: float = 4.6) -> VGroup:
    circles = VGroup(
        Circle(radius=0.82, color=WHITE, stroke_width=2.5).shift(LEFT * 1.22),
        Circle(radius=1.03, color=WHITE, stroke_width=2.5).shift(UP * 0.33),
        Circle(radius=0.76, color=WHITE, stroke_width=2.5).shift(RIGHT * 1.25),
    )
    cover = Rectangle(
        width=width,
        height=1.15,
        stroke_width=0,
        fill_color=BLACK,
        fill_opacity=1,
    ).shift(DOWN * 0.35)
    baseline = Line([-width / 2, -0.63, 0], [width / 2, -0.63, 0], color=WHITE, stroke_width=2.5)
    return VGroup(circles, cover, baseline)


def pulse_along(path: Line | Arrow, color: ManimColor = BLUE, width: float = 6):
    return ShowPassingFlash(path.copy().set_stroke(color, width=width), time_width=0.32)


def flow_arrow(start, end, color: ManimColor = GRAY) -> Arrow:
    return Arrow(start, end, buff=0.18, color=color, stroke_width=2.2, max_tip_length_to_length_ratio=0.12)


class PipelineOverview(Scene):
    """Voice becomes text, reaches the model, and returns as voice."""

    def construct(self) -> None:
        names = ["VOZ", "TEXTO", "IA", "VOZ"]
        symbols = [microphone(0.45), label("Aa", 41), label("✦", 51), speaker(0.43)]
        nodes = VGroup()
        for name, symbol in zip(names, symbols):
            box = card(3.35, 2.15)
            symbol.move_to(box).shift(UP * 0.23)
            name_label = label(name, 21, GRAY).next_to(symbol, DOWN, buff=0.22)
            nodes.add(VGroup(box, symbol, name_label))
        nodes.arrange(DOWN, buff=1.05)

        arrows = VGroup(
            *(flow_arrow(nodes[i].get_bottom(), nodes[i + 1].get_top()) for i in range(3))
        )
        self.play(LaggedStart(*(FadeIn(node, scale=0.82) for node in nodes), lag_ratio=0.14))
        self.play(LaggedStart(*(Create(arrow) for arrow in arrows), lag_ratio=0.16))
        for index, node in enumerate(nodes):
            animations = [
                node[0].animate.set_stroke(BLUE),
                node[1].animate.set_color(BLUE),
            ]
            if index:
                animations.append(pulse_along(arrows[index - 1]))
            self.play(*animations, run_time=0.65)
        self.play(
            LaggedStart(*(node[0].animate.set_stroke(WHITE) for node in nodes), lag_ratio=0.08),
            run_time=0.7,
        )
        self.wait(0.7)


class SpeechToText(Scene):
    """A recorded waveform resolves into a live transcription."""

    def construct(self) -> None:
        mic = microphone(0.65).shift(UP * 5.45)
        wave = waveform(6.6, 1.05).shift(UP * 2.95)
        recording = label("●  GRAVANDO", 20, BLUE).next_to(wave, UP, buff=0.60)
        cursor = Rectangle(width=0.055, height=0.62, fill_color=BLUE, fill_opacity=1, stroke_width=0)
        cursor.move_to(wave.get_left()).shift(LEFT * 0.15)
        self.play(Create(mic), FadeIn(recording))
        self.play(Create(wave), cursor.animate.move_to(wave.get_right()).shift(RIGHT * 0.15), run_time=1.55, rate_func=linear)
        self.play(FadeOut(recording), FadeOut(cursor))

        words = ["Qual", "é", "a", "capital", "do", "Brasil?"]
        rows = VGroup()
        line = VGroup()
        for word in words:
            token = label(word, 33)
            if line.width + token.width + 0.34 > 6.9:
                rows.add(line.arrange(RIGHT, buff=0.34))
                line = VGroup(token)
            else:
                line.add(token)
        rows.add(line.arrange(RIGHT, buff=0.34))
        rows.arrange(DOWN, buff=0.35).move_to(DOWN * 1.25)

        transcribing = label("TRANSCREVENDO", 19, GRAY).next_to(rows, UP, buff=0.80)
        underline = Line([-3.35, -3.05, 0], [3.35, -3.05, 0], color=DIM, stroke_width=2)
        self.play(FadeIn(transcribing), Create(underline))
        self.play(
            wave.animate.set_stroke(DIM),
            LaggedStart(
                *(TransformFromCopy(wave, word) for row in rows for word in row),
                lag_ratio=0.18,
            ),
            run_time=2.1,
        )
        text_box = RoundedRectangle(corner_radius=0.20, width=7.55, height=3.0, stroke_color=BLUE, stroke_width=2)
        text_box.move_to(rows)
        ready = label("TEXTO PRONTO", 20, BLUE).next_to(text_box, DOWN, buff=0.55)
        self.play(Create(text_box), FadeOut(transcribing), FadeIn(ready), run_time=0.75)
        self.wait(0.8)


class OpenRouterHub(Scene):
    """OpenRouter routes the same request to a selectable model."""

    def construct(self) -> None:
        request_box = card(6.4, 1.65)
        request_text = label("Qual é a capital...", 25).move_to(request_box)
        request = VGroup(request_box, request_text).shift(DOWN * 5.55)

        hub_circle = Circle(radius=1.18, stroke_color=WHITE, stroke_width=3)
        hub_text = VGroup(label("OPEN", 23), label("ROUTER", 23, BLUE)).arrange(DOWN, buff=0.06).move_to(hub_circle)
        hub = VGroup(hub_circle, hub_text).shift(DOWN * 1.55)

        model_names = ["MODELO A", "MINIMAX", "MODELO B"]
        models = VGroup()
        for name in model_names:
            model_box = card(2.42, 1.25, GRAY)
            model_text = label(name, 17, GRAY).move_to(model_box)
            models.add(VGroup(model_box, model_text))
        models.arrange(RIGHT, buff=0.30).shift(UP * 3.55)

        inbound = flow_arrow(request.get_top(), hub.get_bottom())
        routes = VGroup(*(flow_arrow(hub.get_top(), model.get_bottom()) for model in models))
        self.play(FadeIn(request, shift=UP * 0.3))
        self.play(Create(inbound), pulse_along(inbound), run_time=0.8)
        self.play(GrowFromCenter(hub))
        self.play(LaggedStart(*(Create(route) for route in routes), lag_ratio=0.12), FadeIn(models))
        for model in models:
            self.play(
                model[0].animate.set_stroke(BLUE),
                model[1].animate.set_color(BLUE),
                run_time=0.32,
            )
            if model is not models[1]:
                self.play(
                    model[0].animate.set_stroke(GRAY),
                    model[1].animate.set_color(GRAY),
                    run_time=0.20,
                )
        selected = label("SELECIONADO", 19, BLUE).next_to(models[1], UP, buff=0.36)
        self.play(pulse_along(routes[1]), FadeIn(selected), run_time=0.9)

        tokens = VGroup(*(label(word, 21, BLUE) for word in ["Brasília", "é", "a", "capital."]))
        tokens.arrange(RIGHT, buff=0.22).to_edge(UP, buff=1.15)
        self.play(LaggedStart(*(FadeIn(token, shift=UP * 0.12) for token in tokens), lag_ratio=0.18))
        self.wait(0.8)


class StreamingComparison(Scene):
    """Waiting for a whole answer is contrasted with streaming chunks."""

    def construct(self) -> None:
        divider = Line([-3.6, 0.15, 0], [3.6, 0.15, 0], color=DIM, stroke_width=2)
        slow_title = label("RESPOSTA INTEIRA", 20, GRAY).move_to([0, 6.3, 0])
        fast_title = label("EM PEDAÇOS", 20, BLUE).move_to([0, -0.75, 0])
        self.play(Create(divider), FadeIn(slow_title), FadeIn(fast_title))

        slow_track = card(6.8, 1.0, GRAY).move_to([0, 3.95, 0])
        slow_fill = Rectangle(width=6.45, height=0.60, stroke_width=0, fill_color=WHITE, fill_opacity=0.75)
        slow_fill.move_to(slow_track).align_to(slow_track, LEFT).shift(RIGHT * 0.17)
        slow_speaker = speaker(0.42).move_to([0, 1.82, 0])
        wait_label = label("esperando...", 19, RED).next_to(slow_track, DOWN, buff=0.45)
        self.play(Create(slow_track), FadeIn(slow_speaker), FadeIn(wait_label))
        self.play(slow_speaker.animate.set_opacity(0.28), GrowFromCenter(slow_fill), run_time=2.3, rate_func=linear)
        self.play(FadeOut(wait_label), slow_speaker.animate.set_opacity(1), run_time=0.35)

        chunks = VGroup(*[
            RoundedRectangle(corner_radius=0.08, width=1.15, height=0.72, stroke_color=BLUE, stroke_width=2)
            for _ in range(5)
        ])
        chunks.arrange(RIGHT, buff=0.18).move_to([0, -3.0, 0])
        fast_speaker = speaker(0.52).move_to([0, -5.45, 0])
        paths = VGroup(*(flow_arrow(chunk.get_bottom(), fast_speaker.get_top(), BLUE) for chunk in chunks))
        self.play(FadeIn(fast_speaker))
        for index, chunk in enumerate(chunks):
            plays = [FadeIn(chunk, shift=RIGHT * 0.18)]
            if index == 0:
                plays.extend([Create(paths[index]), pulse_along(paths[index]), fast_speaker[1].animate.set_opacity(1)])
            else:
                plays.append(pulse_along(paths[index]))
            self.play(*plays, run_time=0.45)
        now = label("COMEÇA ANTES", 22, BLUE).next_to(fast_speaker, DOWN, buff=0.52)
        self.play(FadeIn(now, shift=UP * 0.15))
        self.wait(0.8)


class SentenceAudioQueue(Scene):
    """Tokens form sentences; completed sentences enter TTS immediately."""

    def construct(self) -> None:
        incoming = label("Brasília é a capital. Ela fica...", 24).to_edge(UP, buff=1.15)
        guide = Line([-3.25, 5.95, 0], [3.25, 5.95, 0], color=DIM, stroke_width=2)
        self.play(Create(guide))
        self.play(Write(incoming), run_time=1.45)

        sentence_one = VGroup(card(6.7, 1.32, BLUE), label("Brasília é a capital.", 23, BLUE))
        sentence_two = VGroup(card(6.7, 1.32, GRAY), label("Ela fica no Planalto...", 22, GRAY))
        sentence_one.move_to([0, 2.65, 0])
        sentence_two.move_to([0, 0.65, 0])
        self.play(Transform(incoming, sentence_one), run_time=0.75)
        self.play(FadeIn(sentence_two, shift=DOWN * 0.18))

        tts = VGroup(card(3.2, 1.55), label("TTS", 31, BLUE)).move_to([0, -2.15, 0])
        output = speaker(0.52).move_to([0, -5.25, 0])
        queue_arrow = flow_arrow(sentence_one.get_bottom(), tts.get_top(), BLUE)
        audio_arrow = flow_arrow(tts.get_bottom(), output.get_top(), BLUE)
        self.play(FadeIn(tts), FadeIn(output), Create(queue_arrow), Create(audio_arrow))
        self.play(pulse_along(queue_arrow), incoming.animate.set_opacity(0.35), run_time=0.8)
        self.play(pulse_along(audio_arrow), output[1].animate.set_stroke(BLUE, width=4), run_time=0.75)
        next_sentence = sentence_two.copy().move_to(sentence_one)
        next_sentence[0].set_stroke(BLUE)
        next_sentence[1].set_color(BLUE)
        self.play(
            FadeOut(incoming),
            Transform(sentence_two, next_sentence),
            run_time=0.65,
        )

        more = label("novas palavras chegando...", 18, GRAY).next_to(sentence_two, DOWN, buff=0.42)
        dots = VGroup(*(Dot(radius=0.07, color=BLUE) for _ in range(5))).arrange(RIGHT, buff=0.28)
        dots.next_to(more, DOWN, buff=0.40)
        self.play(FadeIn(more), LaggedStart(*(GrowFromCenter(dot) for dot in dots), lag_ratio=0.18), run_time=1.1)
        self.wait(0.8)


class TextToSpeech(Scene):
    """A text response is synthesized into audio and played by the phone."""

    def construct(self) -> None:
        sentence = label("A resposta chegou.", 31).shift(UP * 4.85)
        text_box = card(7.25, 1.75).move_to(sentence)
        tts = VGroup(card(3.0, 1.55), label("TTS", 34, BLUE)).move_to([0, 1.45, 0])
        wave = waveform(6.5, 1.0).set_color(BLUE).move_to([0, -1.45, 0])
        phone_speaker = speaker(0.72).move_to([0, -4.65, 0])
        first = flow_arrow(text_box.get_bottom(), tts.get_top())
        second = flow_arrow(tts.get_bottom(), wave.get_top(), BLUE)
        third = flow_arrow(wave.get_bottom(), phone_speaker.get_top(), BLUE)

        self.play(Create(text_box), Write(sentence))
        self.play(Create(first), FadeIn(tts), pulse_along(first), run_time=0.9)
        self.play(Create(second), pulse_along(second), Create(wave), run_time=1.0)
        self.play(Create(third), pulse_along(third), FadeIn(phone_speaker), run_time=0.9)
        self.play(
            Succession(
                phone_speaker[1].animate.scale(1.13),
                phone_speaker[1].animate.scale(1 / 1.13),
                phone_speaker[1].animate.scale(1.13),
                phone_speaker[1].animate.scale(1 / 1.13),
            ),
            run_time=1.25,
        )
        self.wait(0.7)


class LocalVsCloud(Scene):
    """Local audio work is separated from the remote model request."""

    def construct(self) -> None:
        cloud_shape = cloud().shift(UP * 5.25)
        cloud_text = VGroup(label("OPENROUTER", 20), label("MINIMAX", 18, BLUE)).arrange(DOWN, buff=0.14)
        cloud_text.move_to(cloud_shape).shift(DOWN * 0.12)
        cloud_group = VGroup(cloud_shape, cloud_text)

        local_boundary = RoundedRectangle(
            corner_radius=0.30,
            width=7.6,
            height=8.25,
            stroke_color=WHITE,
            stroke_width=2.5,
        ).shift(DOWN * 2.2)
        local_title = label("RASPBERRY PI", 20, BLUE)
        local_title.move_to(local_boundary.get_top() + DOWN * 0.46 + LEFT * 2.25)
        local_names = ["GRAVA", "TRANSCREVE", "GERA VOZ", "REPRODUZ"]
        local_cards = VGroup()
        for name in local_names:
            item = VGroup(card(2.85, 1.25, GRAY), label(name, 18, WHITE))
            item[1].move_to(item[0])
            local_cards.add(item)
        local_cards.arrange_in_grid(rows=2, cols=2, buff=(0.38, 0.58)).move_to(local_boundary)
        pi = chip(0.55).next_to(local_cards, DOWN, buff=0.65)

        up_path = DashedLine(local_boundary.get_top(), cloud_group.get_bottom(), color=GRAY, stroke_width=2.2)
        text_packet = VGroup(card(1.65, 0.78, BLUE), label("TEXTO", 15, BLUE))
        text_packet[1].move_to(text_packet[0])
        text_packet.move_to(up_path.get_start())

        self.play(FadeIn(cloud_group), Create(local_boundary), FadeIn(local_title))
        self.play(LaggedStart(*(FadeIn(item, scale=0.84) for item in local_cards), lag_ratio=0.12), FadeIn(pi))
        self.play(
            LaggedStart(
                *(
                    AnimationGroup(
                        item[0].animate.set_stroke(BLUE),
                        item[1].animate.set_color(BLUE),
                    )
                    for item in local_cards
                ),
                lag_ratio=0.12,
            ),
            run_time=0.9,
        )
        self.play(Create(up_path), FadeIn(text_packet))
        self.play(text_packet.animate.move_to(cloud_group.get_bottom()).scale(0.72), run_time=1.15, rate_func=linear)
        response_packet = VGroup(card(1.95, 0.78, BLUE), label("RESPOSTA", 14, BLUE))
        response_packet[1].move_to(response_packet[0])
        response_packet.move_to(cloud_group.get_bottom())
        self.play(FadeOut(text_packet), FadeIn(response_packet))
        self.play(
            response_packet.animate.move_to(local_boundary.get_top() + DOWN * 1.08).scale(0.72),
            run_time=1.15,
            rate_func=linear,
        )
        local_caption = label("ÁUDIO FICA AQUI", 21, BLUE).next_to(local_boundary, DOWN, buff=0.45)
        self.play(FadeIn(local_caption))
        self.wait(0.8)


class FullSystemLoop(Scene):
    """The complete conversation makes one compact trip through the system."""

    def construct(self) -> None:
        stages = [
            ("GRAVANDO", "RASPBERRY", microphone(0.34)),
            ("TRANSCREVENDO", "RASPBERRY", label("Aa", 34)),
            ("PENSANDO", "OPENROUTER", label("✦", 40)),
            ("FALANDO", "RASPBERRY", speaker(0.32)),
        ]
        nodes = VGroup()
        for name, location, symbol in stages:
            box = card(5.9, 1.95, GRAY)
            symbol.move_to(box).shift(LEFT * 1.9)
            name_label = label(name, 19, GRAY).move_to(box).shift(RIGHT * 0.55 + UP * 0.18)
            location_label = label(location, 12, GRAY).next_to(name_label, DOWN, buff=0.16)
            lamp = Circle(radius=0.11, fill_color=GRAY, fill_opacity=1, stroke_width=0)
            lamp.move_to(box.get_right()).shift(LEFT * 0.35)
            nodes.add(VGroup(box, symbol, name_label, location_label, lamp))
        nodes.arrange(DOWN, buff=0.72)
        arrows = VGroup(*(flow_arrow(nodes[i].get_bottom(), nodes[i + 1].get_top()) for i in range(3)))

        self.play(LaggedStart(*(FadeIn(node, shift=UP * 0.18) for node in nodes), lag_ratio=0.12))
        self.play(LaggedStart(*(Create(arrow) for arrow in arrows), lag_ratio=0.14))
        for index, node in enumerate(nodes):
            plays = [
                node[0].animate.set_stroke(BLUE),
                node[1].animate.set_color(BLUE),
                node[2].animate.set_color(BLUE),
                node[3].animate.set_color(BLUE),
                node[4].animate.set_fill(BLUE),
            ]
            if index:
                plays.append(pulse_along(arrows[index - 1]))
            self.play(*plays, run_time=0.65)
            if index < len(nodes) - 1:
                self.play(
                    node[0].animate.set_stroke(GRAY),
                    node[1].animate.set_color(GRAY),
                    node[2].animate.set_color(GRAY),
                    node[3].animate.set_color(GRAY),
                    run_time=0.25,
                )
        history = VGroup(
            label("VOCÊ   Qual é a capital do Brasil?", 17, GRAY),
            label("IA     Brasília.", 19, BLUE),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.25).to_edge(DOWN, buff=0.65)
        self.play(LaggedStart(*(FadeIn(line, shift=UP * 0.12) for line in history), lag_ratio=0.28))
        self.wait(0.8)
