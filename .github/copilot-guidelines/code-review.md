Review with the PortfolioUtils standards in mind:

- Strict typing (mypy strict flags, also in tests), no bare generics, no unjustified `# type: ignore` / `# noqa`.
- Sphinx-style docstrings consistent with the signature (pydoclint), valid doctests.
- Functions small (McCabe <= 7), pure computations separated from I/O, dependency injection for HTTP sessions and paths.
- Credentials never logged, printed or hard-coded; `.env` never read; tests without network.
- Analysis code free of look-ahead bias, explicit annualization, explicit risk-free rate, explicit calendar alignment.
- Tests cover new branches (coverage >= 95% with branches).
