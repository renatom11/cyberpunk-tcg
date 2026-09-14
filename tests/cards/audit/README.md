Audit findings, as failing tests.

Each `test_aNN.py` is written by one audit agent for one batch of card scripts. Three kinds of test
live under this directory and each declares which it is, because "this is how the card behaves" and
"this is how the card should behave" are opposite claims and a directory that mixes them unlabelled
is worse than one that holds only the first.

**A finding** is `@pytest.mark.xfail(strict=True)` with its finding id in the reason. Strict is the
mechanism: the suite stays green while a finding is open, and the moment a fix makes the test pass,
pytest reports XPASS as a failure. A fix therefore cannot land without deleting the marker, and that
deletion is the git record that the test was red before the fix and green after. It replaces "the
agent says it saw it fail" with something the repo enforces.

**A control** is an unmarked, passing test that shows the failing test beside it fails for the
reason claimed rather than because its board was broken — Maelstrom Zealots losing a fight
*decisively* does defeat the winner, so the xfail about a tied fight is genuinely about ties. It
stays next to its finding, where a reader meets both at once, and says so in its first line.

**A confirmation** is what the audit produces when it suspects a card, writes the test, and finds
the engine right. That is coverage the pool did not have, paid for out of the audit, and it is the
class the plan calls S-SUSPICION — the most dangerous to act on, since someone who "knows" a card is
wrong and cannot make it fail will reach for the engine next. Confirmations go in
`test_confirmed_aNN.py`.

Every test here asserts printed-text outcomes only — zones, Gig values, hand size, power, keywords —
and never a script internal. A test asserting a flag bitmask cannot be checked against the card and
so cannot be reviewed at all.

`tests/cards/test_audit_shape.py` enforces all of the above structurally, because every way this
convention decays is green when you run the tests.
