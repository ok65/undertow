"""Playful, code-directed diagnostic roasts with MadLib-style variation."""

from __future__ import annotations

import random


class CodeRoaster:
    """Generate varied severity-specific jokes about an offending code line."""

    word_pools = {
        "useless_noun": (
            "a chocolate teapot", "a soggy firework", "a screen door on a submarine",
            "a GPS with no satellites", "a waterproof teabag", "a one-legged tripod",
            "a punctured lifeboat", "a rubber hammer", "a paper anchor", "a silent foghorn",
            "a square wheel", "a fishnet made of soup", "a parachute made of confetti",
            "a bicycle with no pedals", "a lighthouse with no lamp", "a map of nowhere",
            "a surfboard made of crackers", "a mousetrap for elephants", "an inflatable anvil",
            "a compass glued to a merry-go-round", "a raincoat made of sugar", "a submarine with windows open",
            "a dictionary with no words", "a toaster in a swimming pool", "a lock without a key",
            "a bucket with ambition", "a broken sundial at night", "a parachute for a worm",
            "a snorkel in a desert", "a teacup attempting naval warfare",
        ),
        "bad_adjective": (
            "haunted", "backwards", "cursed", "underwater", "unlicensed", "feral",
            "confused", "flammable", "sideways", "haemorrhaging", "unsupervised", "crooked",
            "damp", "malfunctioning", "questionable", "unhinged", "half-baked", "storm-damaged",
            "off-brand", "inverted", "sleep-deprived", "radioactive", "wobbly", "overconfident",
            "deeply suspicious", "poorly supervised", "structurally dubious", "caffeinated", "slippery",
            "administratively cursed",
        ),
        "disaster_noun": (
            "shipwreck", "punctuation cyclone", "logic swamp", "bracket avalanche", "syntax crater",
            "type-system thunderstorm", "spaghetti reef", "semantic sinkhole", "bug aquarium",
            "maintenance volcano", "control-flow tumbleweed", "exception piñata", "compiler tantrum",
            "readability mudslide", "namespace haunted house", "indentation landslide",
        ),
        "bad_place": (
            "a compiler review", "a code review", "the production branch", "a debugging session",
            "a team handover", "the documentation", "a midnight deploy", "a refactoring sprint",
            "the error log", "a maintenance release", "the test suite", "a serious software project",
        ),
        "verb": (
            "sank", "derailed", "wandered", "collapsed", "mutinied", "face-planted",
            "ran aground", "forgot its trousers", "swerved into traffic", "evaporated", "went feral",
            "got tangled in the rigging",
        ),
    }

    templates = {
        "error": (
            "This code is about as useful as {useless_noun} at a {bad_adjective} festival.",
            "A {disaster_noun} has {verb} into the interpreter, and this line is holding the map.",
            "The parser has declared this a {bad_adjective} {disaster_noun} and requested immediate snacks.",
            "This line {verb} so dramatically that even the traceback wants a stunt double.",
            "A {useless_noun} would make a sturdier foundation for this statement.",
            "The grammar has packed a suitcase and fled this {bad_place}.",
            "This is not a statement; it is a {disaster_noun} wearing punctuation.",
            "The interpreter has seen this line and is now reconsidering its career.",
            "Somewhere, a semicolon is crying into a {bad_adjective} coffee.",
            "This line has the structural integrity of {useless_noun} in a hurricane.",
            "The syntax compass is spinning; this {disaster_noun} has no known coordinates.",
            "A {bad_adjective} seagull could design a more navigable route through this line.",
        ),
        "warning": (
            "This code is technically afloat, but it is dragging a {useless_noun} behind it.",
            "A small {disaster_noun} is squatting here and charging rent in future bugs.",
            "This line is one {bad_adjective} gust away from becoming an incident report.",
            "The code {verb} gently, which is still more movement than maintainability wanted.",
            "A {bad_adjective} plank in the otherwise respectable pier of this function.",
            "This statement has the confidence of {useless_noun} at a planning meeting.",
            "The warning light is blinking because this line packed for {bad_place} without a map.",
            "Not catastrophic, merely a {disaster_noun} practising its entrance.",
            "This code has wandered into the weeds carrying a {useless_noun} and no compass.",
            "A {bad_adjective} shortcut through the swamp of future maintenance.",
            "This line is auditioning for the role of recurring bug in a very small tragedy.",
            "The design is still standing, but it has started leaning like {useless_noun}.",
        ),
        "suggestion": (
            "This code works about as elegantly as {useless_noun} at a {bad_adjective} festival.",
            "A tiny polish pass would turn this {disaster_noun} into a respectable wave.",
            "This line is functional, but dressed like it lost a bet with a {bad_adjective} tailor.",
            "A clearer name would save future readers from a {disaster_noun} expedition.",
            "This statement has the readability of {useless_noun} in fog.",
            "Nothing is on fire; the code is merely carrying a {useless_noun} for no reason.",
            "A little refactoring would stop this line {verb} through the style guide.",
            "This is a perfectly legal shortcut to {bad_place}, with complimentary confusion.",
            "The idea is sound, but the presentation is a {bad_adjective} puppet show.",
            "This line could be clearer than a lighthouse, yet currently resembles {useless_noun}.",
            "A modest improvement would remove one barnacle from this {disaster_noun}.",
            "The code is almost tidy, like {useless_noun} is almost useful in a {bad_place}.",
        ),
    }

    def __init__(self, seed: int | None = None) -> None:
        self._random = random.Random(seed) if seed is not None else random.SystemRandom()

    def roast(self, severity: str) -> str:
        """Return one fresh roast for a severity name."""
        severity = severity if severity in self.templates else "warning"
        template = self._random.choice(self.templates[severity])
        values = {
            placeholder: self._random.choice(options)
            for placeholder, options in self.word_pools.items()
            if "{" + placeholder + "}" in template
        }
        return template.format(**values)
