# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/dahlb/carrier_api/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                              |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|-------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/carrier\_api/\_\_init\_\_.py                  |       10 |        0 |        0 |        0 |    100% |           |
| src/carrier\_api/api\_connection\_graphql.py      |      164 |      122 |       44 |        0 |     20% |39-44, 47, 50-92, 95-98, 101-114, 119-129, 134-183, 188-331, 336-393, 398-407, 410-427, 430-447, 450-467, 470-473, 478-485, 490-493, 521-542, 547-559, 568-579, 582-591, 601-614 |
| src/carrier\_api/api\_websocket.py                |       80 |       53 |       26 |        0 |     25% |33, 36-52, 55, 60-81, 84-94, 97, 100-104 |
| src/carrier\_api/api\_websocket\_data\_updater.py |       67 |       11 |       26 |        7 |     78% |14-\>13, 16, 28-\>27, 30, 45, 69-74, 78-79 |
| src/carrier\_api/config.py                        |      113 |       31 |       30 |        4 |     66% |25, 34, 55-58, 74, 79-83, 89, 94-106, 109-122, 125, 154-\>156, 168, 176 |
| src/carrier\_api/const.py                         |       26 |        0 |        0 |        0 |    100% |           |
| src/carrier\_api/energy.py                        |       53 |        8 |        6 |        0 |     80% |21, 34, 86-89, 92, 107 |
| src/carrier\_api/errors.py                        |        5 |        0 |        0 |        0 |    100% |           |
| src/carrier\_api/profile.py                       |       32 |        2 |        0 |        0 |     94% |    38, 52 |
| src/carrier\_api/status.py                        |       82 |       18 |       16 |        1 |     70% |29-36, 39, 55, 85-\>87, 102-107, 110, 129 |
| src/carrier\_api/stub.py                          |       46 |       46 |        6 |        0 |      0% |      2-69 |
| src/carrier\_api/system.py                        |       16 |        2 |        0 |        0 |     88% |    26, 36 |
| src/carrier\_api/util.py                          |       27 |        3 |        8 |        1 |     89% |15-\>14, 33-35 |
| **TOTAL**                                         |  **721** |  **296** |  **162** |   **13** | **53%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/dahlb/carrier_api/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/dahlb/carrier_api/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/dahlb/carrier_api/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/dahlb/carrier_api/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fdahlb%2Fcarrier_api%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/dahlb/carrier_api/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.