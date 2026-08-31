# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/dahlb/carrier_api/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                              |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|-------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/carrier\_api/\_\_init\_\_.py                  |       12 |        0 |        0 |        0 |    100% |           |
| src/carrier\_api/api\_connection\_graphql.py      |      248 |       24 |       66 |       16 |     87% |97, 151-158, 164, 171, 258-259, 678, 680, 754, 783, 811, 828, 850, 874, 943, 945, 979, 1039, 1051 |
| src/carrier\_api/api\_websocket.py                |       98 |       29 |       28 |        4 |     67% |81-97, 101, 118-\>120, 120-\>140, 121-\>140, 131-\>121, 159-169, 173 |
| src/carrier\_api/api\_websocket\_data\_updater.py |      103 |        9 |       44 |        3 |     90% |146, 170-175, 187-188 |
| src/carrier\_api/config.py                        |      131 |        5 |       32 |        3 |     95% |75, 174, 237, 286, 333-\>335, 382 |
| src/carrier\_api/const.py                         |       27 |        0 |        0 |        0 |    100% |           |
| src/carrier\_api/energy.py                        |      121 |        3 |       22 |        1 |     97% |118, 186, 350 |
| src/carrier\_api/entry\_level.py                  |       46 |        2 |        0 |        0 |     96% |   74, 138 |
| src/carrier\_api/errors.py                        |       13 |        0 |        0 |        0 |    100% |           |
| src/carrier\_api/profile.py                       |       35 |        0 |        0 |        0 |    100% |           |
| src/carrier\_api/status.py                        |      121 |        5 |       24 |        3 |     94% |78, 86, 202, 241-\>243, 245-\>247, 247-\>249, 315, 323 |
| src/carrier\_api/system.py                        |       49 |        2 |        6 |        1 |     95% |  188, 221 |
| src/carrier\_api/util.py                          |       27 |        0 |        8 |        0 |    100% |           |
| **TOTAL**                                         | **1031** |   **79** |  **230** |   **31** | **90%** |           |


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