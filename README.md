# portfolio-utils

This project contains the python package known as "portfolio-utils". It requires Python 3.13.

## Run the application

### Clone the application
Clone the code directly from the repository:
```
git clone https://github.com/NicolaDonelli/PortfolioUtils
cd "$(basename "https://github.com/NicolaDonelli/PortfolioUtils" .git)"
```

### Prerequisites

### Set environment variables
You need to set a few environment variables in your local environment:
```
PROJECT_DIR=PATH_TO_THIS_REPOSITORY
```
This variable contain the path that points to the repository root. The corresponding value is also used in CI/CD workflows

## Repository structure
The repository is organized as follows:
```
PROJECT_DIR                     # Repository root
├── .commitlintrc.yaml          # Commit message rules
├── .devcontainer/              # Development container configuration
│   ├── devcontainer-lock.json  # Pinned container feature versions
│   └── devcontainer.json       # Container setup
├── .dockerignore               # Files excluded from Docker builds
├── .gitattributes              # Git file attributes
├── .github/                    # GitHub and Copilot configuration
│   ├── agents/                 # Specialized coding agents
│   │   ├── code-reviewer.agent.md           # Review agent definition
│   │   ├── investing-data-engineer.agent.md # Downloader agent definition
│   │   ├── planner.agent.md                 # Planning agent definition
│   │   ├── python-implementer.agent.md       # Python implementation agent
│   │   └── quant-analyst.agent.md            # Portfolio analysis agent
│   ├── copilot-guidelines/     # Copilot contribution guidelines
│   │   ├── code-review.md      # Code review guidance
│   │   └── commit-messages.md  # Commit message guidance
│   ├── hooks/                  # Repository automation hooks
│   │   ├── scripts/            # Hook implementations
│   │   │   ├── _hooklib.py       # Shared hook utilities
│   │   │   ├── guard_tool_use.py # Tool-use policy guard
│   │   │   ├── post_edit_lint.py # Post-edit lint hook
│   │   │   ├── quality_gate.py   # Quality-gate hook
│   │   │   └── session_context.py # Session context hook
│   │   ├── context.json        # Session context hook settings
│   │   ├── quality.json        # Quality hook settings
│   │   └── security.json       # Security hook settings
│   ├── instructions/           # Path-specific coding instructions
│   │   ├── analysis.instructions.md       # Analysis package guidance
│   │   ├── download.instructions.md       # Download package guidance
│   │   ├── project-config.instructions.md # Project configuration guidance
│   │   ├── python-source.instructions.md  # Python source guidance
│   │   └── tests.instructions.md          # Test authoring guidance
│   ├── skills/                 # Reusable project workflows
│   │   ├── add-dependency/     # Dependency management workflow
│   │   │   └── SKILL.md        # Dependency skill instructions
│   │   ├── conventional-commit/ # Commit message workflow
│   │   │   └── SKILL.md        # Commit skill instructions
│   │   ├── investing-downloader/ # Investing.com download workflow
│   │   │   ├── reference/      # Downloader reference material
│   │   │   │   ├── csv-schema.md # CSV data schema
│   │   │   │   └── design.md   # Downloader design
│   │   │   └── SKILL.md        # Downloader skill instructions
│   │   ├── portfolio-construction/ # Portfolio construction workflow
│   │   │   ├── reference/      # Portfolio construction references
│   │   │   │   └── methods.md  # Portfolio method descriptions
│   │   │   └── SKILL.md        # Construction skill instructions
│   │   ├── quality-gate/       # Quality checks workflow
│   │   │   ├── scripts/        # Quality gate helper scripts
│   │   │   │   └── run_checks.sh # Run selected quality checks
│   │   │   └── SKILL.md        # Quality gate instructions
│   │   ├── timeseries-analysis/ # Time-series analysis workflow
│   │   │   ├── reference/      # Time-series reference material
│   │   │   │   └── formulas.md # Metric formulas
│   │   │   └── SKILL.md        # Analysis skill instructions
│   │   └── write-tests/        # Test authoring workflow
│   │       ├── SKILL.md        # Test writing instructions
│   │       └── test_template.py # Typed test template
│   ├── workflows/              # CI, release, and documentation workflows
│   │   ├── PyPI-release.yml    # Publish releases to PyPI
│   │   ├── TestPyPI-release.yml # Publish test releases to TestPyPI
│   │   ├── continuous-delivery.yml # Continuous delivery workflow
│   │   ├── continuous-integration.yml # Continuous integration workflow
│   │   └── github-page-build-and-deploy.yml # Build and deploy documentation
│   ├── copilot-instructions.md # Repository-wide Copilot instructions
│   └── RELEASE-TEMPLATE.md     # Release notes template
├── .git_archival.txt           # Git archive metadata
├── .gitignore                  # Files excluded from Git
├── .mcp.json                   # MCP server configuration
├── .pre-commit-config.yaml     # Git hook configuration
├── .vscode/                    # Workspace editor settings
│   └── settings.json           # VS Code workspace configuration
├── Dockerfile                  # Container build instructions
├── LICENSE                     # Project license
├── MANIFEST.in                 # Source distribution file manifest
├── Makefile                    # Development, quality, and documentation commands
├── README.md                   # Project overview and usage guide
├── bin/                        # Executable scripts and utilities
│   ├── 20261101-CompleteExecution.sh # Example full execution script
│   ├── download_investing_etfs.py # Download historical ETF data
│   ├── init_repo.sh            # Initialize the development repository
│   ├── rolling_backtest.py     # Run rolling portfolio backtests
│   └── select_uncorrelated_etfs.py # Select low-correlation ETFs
├── portfolio_utils/            # Typed Python package
│   ├── analysis/               # Time-series analysis and portfolio construction
│   │   ├── __init__.py         # Public analysis API
│   │   ├── _validation.py      # Shared input validation
│   │   ├── backtest.py         # Portfolio backtesting
│   │   ├── loading.py          # Load and align price data
│   │   ├── metrics.py          # Performance and risk metrics
│   │   ├── optimization.py     # Portfolio optimization strategies
│   │   └── returns.py          # Return calculation and resampling
│   ├── download/               # Investing.com data download components
│   │   ├── __init__.py         # Public download API
│   │   ├── cli.py              # Downloader command-line interface
│   │   ├── client.py           # HTTP client and request handling
│   │   ├── downloader.py       # Download orchestration
│   │   ├── errors.py           # Download exception types
│   │   ├── models.py           # Download data models
│   │   ├── source.py           # Investing.com data source
│   │   └── storage.py          # Historical price CSV storage
│   ├── __init__.py             # Package version metadata
│   ├── py.typed                # Marker for typed package support
│   └── settings.py             # Environment-based configuration
├── pyproject.toml              # Package metadata and tool configuration
├── requirements/               # Generated requirements configuration
│   └── .gitignore              # Keep generated requirements out of Git
├── sphinx/                     # Sphinx documentation source and build files
└── tests/                      # Automated tests and recorded fixtures
    ├── integration/            # Opt-in live integration tests
    │   ├── __init__.py         # Integration test package
    │   └── test_investing_com.py # Investing.com integration tests
    ├── unit/                   # Offline unit tests
    │   ├── analysis/           # Analysis and portfolio tests
    │   │   ├── __init__.py     # Analysis test package
    │   │   ├── test_backtest.py # Backtest tests
    │   │   ├── test_loading.py # Price loading tests
    │   │   ├── test_metrics.py # Performance metric tests
    │   │   ├── test_optimization.py # Optimization strategy tests
    │   │   ├── test_optimization_edges.py # Optimization edge cases
    │   │   ├── test_optimization_validation.py # Optimization input validation tests
    │   │   ├── test_returns.py # Return calculation tests
    │   │   └── test_validation.py # Shared validation tests
    │   ├── cli/                # Command-line interface tests
    │   │   ├── __init__.py     # CLI test package
    │   │   └── test_analysis_cli.py # Analysis CLI tests
    │   ├── download/           # Downloader component tests
    │   │   ├── __init__.py     # Download test package
    │   │   ├── test_cli.py     # Downloader CLI tests
    │   │   ├── test_client.py  # HTTP client tests
    │   │   ├── test_downloader.py # Download orchestration tests
    │   │   ├── test_investing_source.py # Data source tests
    │   │   └── test_storage.py # CSV storage tests
    │   ├── resources/          # Test fixtures
    │   │   └── investing/      # Recorded Investing.com responses
    │   │       ├── etf_category_row_ok.html # ETF category page fixture
    │   │       ├── etf_index_ok.html # ETF index page fixture
    │   │       └── historical_daily_ok.json # Historical prices fixture
    │   ├── __init__.py         # Unit test package
    │   └── test_settings.py    # Settings tests
    └── __init__.py             # Test package
```

## ETF data and portfolio analysis

The tecnical documentation for the current repository is available on the Github Page: https://nicoladonelli.github.io/PortfolioUtils/

The executable scripts in `bin/` can download ETF history, select instruments by
correlation, and run rolling portfolio backtests. Run any script with `--help`
to see all its options.

### Downloading Investing.com history

_*To work, the download module requires valid credentials stored in a .env file directly under repo root defining the values for INVESTING_EMAIL and INVESTING_PASSWORD variables*_

Pass one or more ETF tickers or ISINs to download specific instruments:

```bash
python bin/download_investing_etfs.py SPY IE00B4L5Y983 \
  --start 2015-01-01 --end 2025-12-31 --output data/selected
```

Dates are inclusive and use `YYYY-MM-DD`. If no identifiers are supplied, the
downloader enumerates Investing.com's public ETF catalog and skips listed
instruments that have no history. Catalog coverage depends on the public pages
and pagination exposed by Investing.com and is **not guaranteed to be
exhaustive**. Omitting either date uses the first or latest available observation
for each instrument. Without `--output`, CSVs are written under
`data/YYYYMMDD/` using the UTC download date; filenames follow
`NAME_YYYYMMDD_YYYYMMDD.csv`. Each CSV contains `date, open, high, low, close,
volume`.

### Portfolio analysis

The analysis loaders accept a directory of these CSV files and align instruments
on their common price dates. To select a deterministic subset whose pairwise
absolute simple-return correlations are strictly below 0.4:

```bash
python bin/select_uncorrelated_etfs.py --data-dir data/selected \
  --max-abs-correlation 0.4
```

Use `--instruments file1.csv file2.csv` to restrict the input to named CSV files
(stems without `.csv` are also accepted). Optional `--start-date` and
`--end-date` restrict the correlation period; by default the script uses the
first and last dates common to all selected instruments. It prints the selected
names and their correlation matrix.

Run a rolling-window validation followed by a separate out-of-sample evaluation:

```bash
python bin/rolling_backtest.py --data-dir data/selected \
  --strategy max_sharpe --train-years 3 --validation-years 1
```

The rolling defaults are a three-year training window, one-year non-overlapping
validation windows, and all eight implemented metrics. The default rolling
period starts at the first common date and ends one year and one day before the
last common date; out-of-sample evaluation starts on the next common trading
date. The script prints final portfolio weights, validation-period metric
averages, and out-of-sample metrics. Target strategies require their target
argument (`--target-volatility` for `efficient_risk`, `--target-return` for
`efficient_return`, `efficient_cvar`, and `efficient_semivariance`). The
`black_litterman` strategy requires one of `--market-caps` or
`--prior-returns`, plus either `--absolute-views` or one or more `--relative-view`
arguments.

The optimization API also provides `min_volatility`,
`max_quadratic_utility`, `min_cvar`, `min_semivariance`, `hrp`, and
`black_litterman`. Performance metrics are cumulative and annualized return,
realized and annualized realized volatility, Sharpe and annualized Sharpe ratio,
and Sortino and annualized Sortino ratio. See `--help` and the
`portfolio_utils.analysis` package for strategy inputs and metric conventions.


## GNU Make
This project uses [GNU make](https://www.gnu.org/software/make/) to orchestrate of some complex common actions. 
In particular the processes of compiling and installing requirements, running checks (static typing, linting, unittests, etc), 
compiling documentation, building a docker image and running it are streamlined within the Makefile and can be run using 
simple make commands.
To get a complete list of available make commands the user can simply type `make help` but the most relevant are:
* ``make setup``, to setup the minimal environment required for the application
* ``make setup_dev``, to setup the full development environment (i.e. including dependencies required for quality checks)
* ``make install``, to install the package with minimal requirements
* ``make install_dev``, to install the package with development requirements
* ``make checks``, to check formatting, linting, static typing and running unit-tests
* ``make docs``, to build and compile html documentation using sphinx
* ``make changelogs``, to compile changelogs 
* ``make tag``, to create and push on origin a 'development' git tag with current package version

## Tools for the project
All the configurations for the following tools are contained in ``pyproject.toml`` file.

### Requirements tracking
This project uses [uv](https://github.com/astral-sh/uv) to handle requirements. 
In particular, we define the package requirements, optional extra requirements and dependency groups in the `pyproject.toml` 
configuration file, and we use `uv pip compile` to compile the complete sets of closed requirements for the package and the
development environment (to be used only for reference!) and save them in the `requirements` folder as ``requirements.txt`` 
and ``requirements_dev.txt`` files.

### Coding style
This project uses [ruff](https://github.com/astral-sh/ruff) for formatting and enforcing a coding style.
Run ``make format`` to reformat all source code and tests files to adhere to PEP8 standards.

### Code analysis
This project uses [ruff](https://github.com/astral-sh/ruff) for static code analysis and [pydoclint](https://github.com/jsh9/pydoclint) to analyse docstrings.
Default configurations for ``ruff`` are the ones suggested by the ``ruff`` developers themselves while the default docstring format checked with ``pydoclint`` is ``'sphinx'``. 
Note that default  ``ruff`` configurations include also the ``S`` rule set that check for security issues.
Run ``make lint`` to analyse all source code and tests files.

### Static type checking
This project uses [mypy](https://github.com/python/mypy) for static type checking.
The default configurations for this tool are quite strict. In particular we set the following flags to true:
* explicit_package_bases: This flag tells mypy that top-level packages will be based in either the current directory, or a member of the MYPYPATH environment variable or mypy_path config option. This option is only useful in the absence of __init__.py. See [Mapping file paths](https://mypy.readthedocs.io/en/stable/running_mypy.html#mapping-paths-to-modules) to modules for details.
* namespace_packages: Enables import discovery of namespace packages (see [PEP 420](https://peps.python.org/pep-0420/)). In particular, this prevents discovery of packages that don’t have an __init__.py (or __init__.pyi) file. his flag affects how mypy finds modules and packages explicitly passed on the command line. It also affects how mypy determines fully qualified module names for files passed on the command line. See [Mapping file paths to modules](https://mypy.readthedocs.io/en/stable/running_mypy.html#mapping-paths-to-modules) for details.
* disallow_untyped_calls: Disallows calling functions without type annotations from functions with type annotations.
* disallow_untyped_defs: Disallows defining functions without type annotations or with incomplete type annotations.
* disallow_untyped_decorators: Reports an error whenever a function with type annotations is decorated with a decorator without annotations.
* disallow_any_generics: Disallows usage of generic types that do not specify explicit type parameters.
* disallow_subclassing_any: Disallows subclassing a value of type Any.
* warn_unused_configs: Warns about per-module sections in the config file that do not match any files processed when invoking mypy.
* warn_redundant_casts: Warns about casting an expression to its inferred type.
* warn_unused_ignores: Warns about unneeded # type: ignore comments.
* warn_return_any: Shows a warning when returning a value with type Any from a function declared with a non- Any return type.
* implicit_reexport: By default, imported values to a module are treated as exported and mypy allows other modules to import them. When false, mypy will not re-export unless the item is imported using from-as or is included in __all__. Note that mypy treats stub files as if this is always disabled.
* strict_equality: Prohibit equality checks, identity checks, and container checks between non-overlapping types.
Run ``make mypy`` to analyse all source code and tests files.

### License compatibility checks
This project uses [`licensecheck`](https://github.com/FHPythonUtils/LicenseCheck) to check compatibility between the license of this package and the ones of its depencencies.

### Unit-testing
This project uses [`pytest`](https://docs.pytest.org/en/stable/) for tests. Unit tests are in `tests/unit/` and run offline with `make tests`; this is the test target included in `make checks`.

Live integration tests are in `tests/integration/`. They make real requests to Investing.com and are deliberately excluded from `make checks`. Run them explicitly with `make integration` when network access and a live site check are appropriate.

### Documentation
This project uses [`Sphinx`](https://www.sphinx-doc.org/en/master/) as a tool to create documentation. 
Run `make docs` to automatically build documentation in html format.
There is a Github workflow setup to publish documentation on the repo's Github Page at every push on `main` branch. 
To let this action run smoothly there must exist the `gh_pages`branch and the Github Page must be manually setted (from
github repo web interface > Settings > Pages) to use `gh_pages` as source branch and `/root` as source folder. 
Since this action requires a GITHUB_TOKEN, for its first run in the repo it will be necessary to follow the steps 
detailed [here]( https://github.com/peaceiris/actions-gh-pages#%EF%B8%8F-first-deployment-with-github_token) to make the action run fine from then on.

### Semantic Versioning
This project automatically applies semantic versioning based on tags following PEP440 using [`setuptools_scm`](https://github.com/pypa/setuptools_scm).

### Changelog generation
This project uses [`git-cliff`](https://github.com/orhun/git-cliff) to automatically generate changelogs. 
This tool is configured to take into account commit messages following the [conventional-commits](https://www.conventionalcommits.org/) standard.

## Git hooks
This project uses [`pre-commit`](https://github.com/pre-commit/pre-commit), as configured in `.pre-commit-config.yaml` file, to run git hooks at different stages.
In particular, we define the following hooks:
* checks: runs the local ``make checks`` command at pre-push stage.
* detect-secrets: uses [`detect-secrets`](https://github.com/Yelp/detect-secrets) to automatically search for secrets versioned in the current diff. It runs at pre-commit stage.
* commitlint: uses [`commitlint`](https://github.com/alessandrojcm/commitlint-pre-commit-hook) to check, at commit-msg stage, that commit message follows the [conventional-commits](https://www.conventionalcommits.org/) standard as configured in the `.commitlintrc.yaml` file. 
Specifically:
  - Commits must start with a type, such as "chore", "fix", "feat", "doc", "perf", "refactor", "style" or "test" followed by an OPTIONAL scope in parentheses, an OPTIONAL exclamation mark "!" to indicate non-backward-compatible changes (a.k.a. "Breaking Changes"), and a colon and a space (": ") which are both REQUIRED.
  - The "chore" type should be used when a commit represents an insignificant internal change (i.e., a change that does not directly impact how the user interacts with the application).
  - The "fix" type should be used when a commit represents a bugfix to the application (i.e., a change that either doesn't directly impact the user or corrects an error).
  - The "feat" type should be used when a commit adds a new feature to the application (i.e., an addition that directly impacts how the user interacts with the application).
  - A scope CAN be included in parentheses after the type. A scope typically consists of a single word indicating a code module affected by the commit or a Jira task identifier, e.g., "fix(parser):" or "fix(prjaiaas-134)".
  - The description MUST immediately follow the colon-space ": " after the prefix containing the type and, optionally, the scope. It MUST end with a period (dot). The description is a brief summary in ENGLISH of the code changes. E.g., "fix: solved parsing issues with multiple spaces in strings.". 
  - A longer commit body CAN be provided after the description to give additional information about the changes made to the code (particularly useful for very large commits). The body MUST start with a blank line after the description and MUST be written in ENGLISH. 
  - The commit body is in free form and MAY consist of any number of paragraphs separated by a new line. 
  - One or more footers CAN be provided on a blank line after the commit body. Each footer MUST consist of a single-word token followed by ": " or " #", followed by a string (this is inspired by the git trailer convention). 
  - A footer token MUST use the dash ("-") character instead of spaces, for example Acked-by (this helps differentiate the footer section from a multi-paragraph commit body). An exception is made for "BREAKING CHANGE", which MAY also be used as a footer token. 
  - A footer's value CAN contain spaces and newlines: the automatic parsing of a footer MUST stop when the next valid token/separator pair of the next footer is observed. 
  - Breaking changes MUST be indicated in the commit's type/scope prefix, or as a specific footer entry. 
  - If included as a footer, Breaking Changes MUST start with the token "BREAKING CHANGE: " followed by a description of the change, e.g., BREAKING CHANGE: environment variables now have precedence over configuration files. 
  - If included in the prefix with the type and, optionally, scope, breaking changes MUST be indicated with an exclamation mark "!" immediately before the colon ":" that concludes the prefix. If "!" is used, "BREAKING CHANGE: " CAN be omitted from the footer section, and the description MUST be used to describe the breaking change.
  - "BREAKING-CHANGE" MUST be synonymous with "BREAKING CHANGE" when used as a footer token.

## Continuous Integration and Continuous Delivery
CI/CD workflows can be performed with GithubActions.

### CI workflow
This workflow is activated only by commits on an open Pull Request and checks the application, by running ``make checks`` on checked-out code.

### Github page build and deploy workflow
This workflow is activated by each commit pushed on the main branch. It compiles the technical docs and deploys the updated Github page at https://nicoladonelli.github.io/PortfolioUtils/