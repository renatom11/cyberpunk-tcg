Audit findings, as failing tests.

Each file is written by one audit agent for one batch of card scripts, and every test in it is
marked `@pytest.mark.xfail(strict=True)` with the finding id in its reason. Strict is the point:
the suite stays green while a finding is open, and the moment a fix makes the test pass, pytest
reports XPASS as a failure. A fix therefore cannot land without deleting the marker, and that
deletion is the git record that the test was red before the fix and green after.

Tests here assert printed-text outcomes only — zones, gig values, hand size, power, keywords —
never script internals.
