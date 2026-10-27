#!/usr/bin/env python3
"""Exhaustively verify lifecycle state values and valid transitions."""

import unittest

from file_lifecycle import FileState, VALID_TRANSITIONS, can_transition, transition_state


EXPECTED = {
    "queued": {"scanning", "blocked"},
    "scanning": {"analyzing", "blocked"},
    "analyzing": {"ready", "blocked"},
    "blocked": set(),
    "ready": {"opening", "blocked"},
    "opening": {"completed", "blocked"},
    "completed": set(),
}


class FileLifecycleTests(unittest.TestCase):
    def test_all_states_have_the_required_stable_values(self):
        self.assertEqual({state.value for state in FileState}, set(EXPECTED))
        self.assertEqual(len(FileState), 7)
        for state in FileState:
            self.assertEqual(FileState(state.value), state)

    def test_complete_transition_matrix(self):
        self.assertEqual(set(VALID_TRANSITIONS), set(FileState))
        for current in FileState:
            self.assertEqual({state.value for state in VALID_TRANSITIONS[current]},
                             EXPECTED[current.value])
            for target in FileState:
                permitted = target.value in EXPECTED[current.value]
                with self.subTest(current=current.value, target=target.value):
                    self.assertEqual(can_transition(current, target), permitted)
                    if permitted:
                        self.assertIs(transition_state(current, target), target)
                    else:
                        with self.assertRaises(ValueError):
                            transition_state(current, target)

    def test_successful_path_reaches_completion_in_order(self):
        state = FileState.QUEUED
        for next_state in (FileState.SCANNING, FileState.ANALYZING, FileState.READY,
                           FileState.OPENING, FileState.COMPLETED):
            state = transition_state(state, next_state)
        self.assertIs(state, FileState.COMPLETED)

    def test_blocked_terminal_from_every_nonterminal_state(self):
        for current in (FileState.QUEUED, FileState.SCANNING, FileState.ANALYZING,
                        FileState.READY, FileState.OPENING):
            with self.subTest(current=current.value):
                self.assertIs(transition_state(current, FileState.BLOCKED),
                              FileState.BLOCKED)
        for terminal in (FileState.BLOCKED, FileState.COMPLETED):
            self.assertEqual(VALID_TRANSITIONS[terminal], frozenset())

    def test_invalid_values_cannot_bypass_transition_checks(self):
        for current, target in (("queued", FileState.SCANNING),
                                (FileState.QUEUED, "scanning"),
                                ("unexpected", FileState.READY),
                                (None, FileState.BLOCKED)):
            with self.subTest(current=current, target=target):
                self.assertFalse(can_transition(current, target))
                with self.assertRaises(ValueError):
                    transition_state(current, target)
        with self.assertRaises(ValueError):
            FileState("unrecognized")

    def test_transition_table_is_immutable(self):
        with self.assertRaises(TypeError):
            VALID_TRANSITIONS[FileState.QUEUED] = frozenset()
        with self.assertRaises(AttributeError):
            VALID_TRANSITIONS[FileState.QUEUED].add(FileState.COMPLETED)


if __name__ == "__main__":
    unittest.main()
