├── .gitignore
├── .travis.yml
├── CONTRIBUTING.rst
├── LICENSE
├── MANIFEST.in
├── README.rst
├── docs
    ├── Makefile
    └── source
    │   ├── conf.py
    │   ├── index.rst
    │   └── matrix_client.rst
├── matrix_client
    ├── __init__.py
    ├── api.py
    ├── checks.py
    ├── client.py
    ├── crypto
    │   ├── __init__.py
    │   ├── olm_device.py
    │   └── one_time_keys.py
    ├── errors.py
    ├── room.py
    └── user.py
├── samples
    ├── ChangeDisplayName.py
    ├── GetUserProfile.py
    ├── SetRoomProfile.py
    ├── SimpleChatClient.py
    ├── UserPassOrTokenClient.py
    └── samples_common.py
├── setup.cfg
├── setup.py
└── test
    ├── __init__.py
    ├── api_test.py
    ├── client_test.py
    ├── crypto
        └── olm_device_test.py
    ├── response_examples.py
    └── user_test.py


/.gitignore:
--------------------------------------------------------------------------------
 1 | # Byte-compiled / optimized / DLL files
 2 | __pycache__/
 3 | *.py[cod]
 4 | 
 5 | # C extensions
 6 | *.so
 7 | 
 8 | # Distribution / packaging
 9 | .Python
10 | env/
11 | build/
12 | develop-eggs/
13 | dist/
14 | downloads/
15 | eggs/
16 | lib/
17 | lib64/
18 | parts/
19 | sdist/
20 | var/
21 | *.egg-info/
22 | .installed.cfg
23 | *.egg
24 | 
25 | # PyInstaller
26 | #  Usually these files are written by a python script from a template
27 | #  before PyInstaller builds the exe, so as to inject date/other infos into it.
28 | *.manifest
29 | *.spec
30 | 
31 | # Installer logs
32 | pip-log.txt
33 | pip-delete-this-directory.txt
34 | 
35 | # Unit test / coverage reports
36 | htmlcov/
37 | .tox/
38 | .coverage
39 | .cache
40 | nosetests.xml
41 | coverage.xml
42 | 
43 | # Translations
44 | *.mo
45 | *.pot
46 | 
47 | # Django stuff:
48 | *.log
49 | 
50 | # Sphinx documentation
51 | docs/build/
52 | 
53 | # PyBuilder
54 | target/
55 | 


--------------------------------------------------------------------------------
/.travis.yml:
--------------------------------------------------------------------------------
 1 | language: python
 2 | python:
 3 |   - "2.7"
 4 |   - "3.5"
 5 |   - "3.6"
 6 |   - "3.7"
 7 | 
 8 | before_install:
 9 |   - wget https://gitlab.matrix.org/matrix-org/olm/-/archive/3.1.2/olm-3.1.2.tar.bz2
10 |   - tar -xvf olm-3.1.2.tar.bz2
11 |   - pushd olm-3.1.2 && make && sudo make PREFIX="/usr" install && popd
12 |   - rm -r olm-3.1.2
13 | 
14 | install:
15 |   - pip install -U coveralls
16 |   - pip install -U flake8
17 |   - pip install -U check-manifest
18 |   - pip install ".[test, doc, e2e]"
19 | 
20 | script:
21 |   - flake8 matrix_client samples test
22 |   - check-manifest
23 |   - coverage run --source=matrix_client setup.py test
24 |   - sphinx-build -W docs/source docs/build/html
25 | 
26 | after_sucess:
27 |   - coverage report
28 |   - coveralls
29 | 


--------------------------------------------------------------------------------
/CONTRIBUTING.rst:
--------------------------------------------------------------------------------
  1 | Contributing code to Matrix
  2 | ===========================
  3 | 
  4 | Everyone is welcome to contribute code to Matrix
  5 | (https://github.com/matrix-org), provided that they are willing to license
  6 | their contributions under the same license as the project itself. We follow a
  7 | simple 'inbound=outbound' model for contributions: the act of submitting an
  8 | 'inbound' contribution means that the contributor agrees to license the code
  9 | under the same terms as the project's overall 'outbound' license - in our
 10 | case, this is almost always Apache Software License v2 (see LICENSE).
 11 | 
 12 | Code style
 13 | ~~~~~~~~~~
 14 | 
 15 | All Matrix projects have a well-defined code-style - and sometimes we've even
 16 | got as far as documenting it... For instance, synapse's code style doc lives
 17 | at https://github.com/matrix-org/synapse/tree/master/docs/code_style.rst.
 18 | 
 19 | Please ensure your changes match the cosmetic style of the existing project,
 20 | and **never** mix cosmetic and functional changes in the same commit, as it
 21 | makes it horribly hard to review otherwise.
 22 | 
 23 | Attribution
 24 | ~~~~~~~~~~~
 25 | 
 26 | Everyone who contributes anything to Matrix is welcome to be listed in the
 27 | AUTHORS.rst file for the project in question. Please feel free to include a
 28 | change to AUTHORS.rst in your pull request to list yourself and a short
 29 | description of the area(s) you've worked on. Also, we sometimes have swag to
 30 | give away to contributors - if you feel that Matrix-branded apparel is missing
 31 | from your life, please mail us your shipping address to matrix at matrix.org
 32 | and we'll try to fix it :)
 33 | 
 34 | Sign off
 35 | ~~~~~~~~
 36 | 
 37 | In order to have a concrete record that your contribution is intentional and you
 38 | agree to license it under the same terms as the project's license, we've adopted
 39 | the same lightweight approach that the Linux Kernel
 40 | (https://www.kernel.org/doc/Documentation/SubmittingPatches), Docker
 41 | (https://github.com/docker/docker/blob/master/CONTRIBUTING.md), and many other
 42 | projects use: the DCO (Developer Certificate of Origin:
 43 | http://developercertificate.org/). This is a simple declaration that you wrote
 44 | the contribution or otherwise have the right to contribute it to Matrix::
 45 | 
 46 |     Developer Certificate of Origin
 47 |     Version 1.1
 48 | 
 49 |     Copyright (C) 2004, 2006 The Linux Foundation and its contributors.
 50 |     660 York Street, Suite 102,
 51 |     San Francisco, CA 94110 USA
 52 | 
 53 |     Everyone is permitted to copy and distribute verbatim copies of this
 54 |     license document, but changing it is not allowed.
 55 | 
 56 |     Developer's Certificate of Origin 1.1
 57 | 
 58 |     By making a contribution to this project, I certify that:
 59 | 
 60 |     (a) The contribution was created in whole or in part by me and I
 61 |         have the right to submit it under the open source license
 62 |         indicated in the file; or
 63 | 
 64 |     (b) The contribution is based upon previous work that, to the best
 65 |         of my knowledge, is covered under an appropriate open source
 66 |         license and I have the right under that license to submit that
 67 |         work with modifications, whether created in whole or in part
 68 |         by me, under the same open source license (unless I am
 69 |         permitted to submit under a different license), as indicated
 70 |         in the file; or
 71 | 
 72 |     (c) The contribution was provided directly to me by some other
 73 |         person who certified (a), (b) or (c) and I have not modified
 74 |         it.
 75 | 
 76 |     (d) I understand and agree that this project and the contribution
 77 |         are public and that a record of the contribution (including all
 78 |         personal information I submit with it, including my sign-off) is
 79 |         maintained indefinitely and may be redistributed consistent with
 80 |         this project or the open source license(s) involved.
 81 | 
 82 | If you agree to this for your contribution, then all that's needed is to
 83 | include the line in your commit or pull request comment::
 84 | 
 85 |     Signed-off-by: Your Name <your@email.example.org>
 86 | 
 87 | ...using your real name; unfortunately pseudonyms and anonymous contributions
 88 | can't be accepted. Git makes this trivial - just use the -s flag when you do
 89 | ``git commit``, having first set ``user.name`` and ``user.email`` git configs
 90 | (which you should have done anyway :)
 91 | 
 92 | Conclusion
 93 | ~~~~~~~~~~
 94 | 
 95 | That's it!  Matrix is a very open and collaborative project as you might expect
 96 | given our obsession with open communication.  If we're going to successfully
 97 | matrix together all the fragmented communication technologies out there we are
 98 | reliant on contributions and collaboration from the community to do so.  So
 99 | please get involved - and we hope you have as much fun hacking on Matrix as we
100 | do!
101 | 


--------------------------------------------------------------------------------
/LICENSE:
--------------------------------------------------------------------------------
  1 | Apache License
  2 |                            Version 2.0, January 2004
  3 |                         http://www.apache.org/licenses/
  4 | 
  5 |    TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION
  6 | 
  7 |    1. Definitions.
  8 | 
  9 |       "License" shall mean the terms and conditions for use, reproduction,
 10 |       and distribution as defined by Sections 1 through 9 of this document.
 11 | 
 12 |       "Licensor" shall mean the copyright owner or entity authorized by
 13 |       the copyright owner that is granting the License.
 14 | 
 15 |       "Legal Entity" shall mean the union of the acting entity and all
 16 |       other entities that control, are controlled by, or are under common
 17 |       control with that entity. For the purposes of this definition,
 18 |       "control" means (i) the power, direct or indirect, to cause the
 19 |       direction or management of such entity, whether by contract or
 20 |       otherwise, or (ii) ownership of fifty percent (50%) or more of the
 21 |       outstanding shares, or (iii) beneficial ownership of such entity.
 22 | 
 23 |       "You" (or "Your") shall mean an individual or Legal Entity
 24 |       exercising permissions granted by this License.
 25 | 
 26 |       "Source" form shall mean the preferred form for making modifications,
 27 |       including but not limited to software source code, documentation
 28 |       source, and configuration files.
 29 | 
 30 |       "Object" form shall mean any form resulting from mechanical
 31 |       transformation or translation of a Source form, including but
 32 |       not limited to compiled object code, generated documentation,
 33 |       and conversions to other media types.
 34 | 
 35 |       "Work" shall mean the work of authorship, whether in Source or
 36 |       Object form, made available under the License, as indicated by a
 37 |       copyright notice that is included in or attached to the work
 38 |       (an example is provided in the Appendix below).
 39 | 
 40 |       "Derivative Works" shall mean any work, whether in Source or Object
 41 |       form, that is based on (or derived from) the Work and for which the
 42 |       editorial revisions, annotations, elaborations, or other modifications
 43 |       represent, as a whole, an original work of authorship. For the purposes
 44 |       of this License, Derivative Works shall not include works that remain
 45 |       separable from, or merely link (or bind by name) to the interfaces of,
 46 |       the Work and Derivative Works thereof.
 47 | 
 48 |       "Contribution" shall mean any work of authorship, including
 49 |       the original version of the Work and any modifications or additions
 50 |       to that Work or Derivative Works thereof, that is intentionally
 51 |       submitted to Licensor for inclusion in the Work by the copyright owner
 52 |       or by an individual or Legal Entity authorized to submit on behalf of
 53 |       the copyright owner. For the purposes of this definition, "submitted"
 54 |       means any form of electronic, verbal, or written communication sent
 55 |       to the Licensor or its representatives, including but not limited to
 56 |       communication on electronic mailing lists, source code control systems,
 57 |       and issue tracking systems that are managed by, or on behalf of, the
 58 |       Licensor for the purpose of discussing and improving the Work, but
 59 |       excluding communication that is conspicuously marked or otherwise
 60 |       designated in writing by the copyright owner as "Not a Contribution."
 61 | 
 62 |       "Contributor" shall mean Licensor and any individual or Legal Entity
 63 |       on behalf of whom a Contribution has been received by Licensor and
 64 |       subsequently incorporated within the Work.
 65 | 
 66 |    2. Grant of Copyright License. Subject to the terms and conditions of
 67 |       this License, each Contributor hereby grants to You a perpetual,
 68 |       worldwide, non-exclusive, no-charge, royalty-free, irrevocable
 69 |       copyright license to reproduce, prepare Derivative Works of,
 70 |       publicly display, publicly perform, sublicense, and distribute the
 71 |       Work and such Derivative Works in Source or Object form.
 72 | 
 73 |    3. Grant of Patent License. Subject to the terms and conditions of
 74 |       this License, each Contributor hereby grants to You a perpetual,
 75 |       worldwide, non-exclusive, no-charge, royalty-free, irrevocable
 76 |       (except as stated in this section) patent license to make, have made,
 77 |       use, offer to sell, sell, import, and otherwise transfer the Work,
 78 |       where such license applies only to those patent claims licensable
 79 |       by such Contributor that are necessarily infringed by their
 80 |       Contribution(s) alone or by combination of their Contribution(s)
 81 |       with the Work to which such Contribution(s) was submitted. If You
 82 |       institute patent litigation against any entity (including a
 83 |       cross-claim or counterclaim in a lawsuit) alleging that the Work
 84 |       or a Contribution incorporated within the Work constitutes direct
 85 |       or contributory patent infringement, then any patent licenses
 86 |       granted to You under this License for that Work shall terminate
 87 |       as of the date such litigation is filed.
 88 | 
 89 |    4. Redistribution. You may reproduce and distribute copies of the
 90 |       Work or Derivative Works thereof in any medium, with or without
 91 |       modifications, and in Source or Object form, provided that You
 92 |       meet the following conditions:
 93 | 
 94 |       (a) You must give any other recipients of the Work or
 95 |           Derivative Works a copy of this License; and
 96 | 
 97 |       (b) You must cause any modified files to carry prominent notices
 98 |           stating that You changed the files; and
 99 | 
100 |       (c) You must retain, in the Source form of any Derivative Works
101 |           that You distribute, all copyright, patent, trademark, and
102 |           attribution notices from the Source form of the Work,
103 |           excluding those notices that do not pertain to any part of
104 |           the Derivative Works; and
105 | 
106 |       (d) If the Work includes a "NOTICE" text file as part of its
107 |           distribution, then any Derivative Works that You distribute must
108 |           include a readable copy of the attribution notices contained
109 |           within such NOTICE file, excluding those notices that do not
110 |           pertain to any part of the Derivative Works, in at least one
111 |           of the following places: within a NOTICE text file distributed
112 |           as part of the Derivative Works; within the Source form or
113 |           documentation, if provided along with the Derivative Works; or,
114 |           within a display generated by the Derivative Works, if and
115 |           wherever such third-party notices normally appear. The contents
116 |           of the NOTICE file are for informational purposes only and
117 |           do not modify the License. You may add Your own attribution
118 |           notices within Derivative Works that You distribute, alongside
119 |           or as an addendum to the NOTICE text from the Work, provided
120 |           that such additional attribution notices cannot be construed
121 |           as modifying the License.
122 | 
123 |       You may add Your own copyright statement to Your modifications and
124 |       may provide additional or different license terms and conditions
125 |       for use, reproduction, or distribution of Your modifications, or
126 |       for any such Derivative Works as a whole, provided Your use,
127 |       reproduction, and distribution of the Work otherwise complies with
128 |       the conditions stated in this License.
129 | 
130 |    5. Submission of Contributions. Unless You explicitly state otherwise,
131 |       any Contribution intentionally submitted for inclusion in the Work
132 |       by You to the Licensor shall be under the terms and conditions of
133 |       this License, without any additional terms or conditions.
134 |       Notwithstanding the above, nothing herein shall supersede or modify
135 |       the terms of any separate license agreement you may have executed
136 |       with Licensor regarding such Contributions.
137 | 
138 |    6. Trademarks. This License does not grant permission to use the trade
139 |       names, trademarks, service marks, or product names of the Licensor,
140 |       except as required for reasonable and customary use in describing the
141 |       origin of the Work and reproducing the content of the NOTICE file.
142 | 
143 |    7. Disclaimer of Warranty. Unless required by applicable law or
144 |       agreed to in writing, Licensor provides the Work (and each
145 |       Contributor provides its Contributions) on an "AS IS" BASIS,
146 |       WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
147 |       implied, including, without limitation, any warranties or conditions
148 |       of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
149 |       PARTICULAR PURPOSE. You are solely responsible for determining the
150 |       appropriateness of using or redistributing the Work and assume any
151 |       risks associated with Your exercise of permissions under this License.
152 | 
153 |    8. Limitation of Liability. In no event and under no legal theory,
154 |       whether in tort (including negligence), contract, or otherwise,
155 |       unless required by applicable law (such as deliberate and grossly
156 |       negligent acts) or agreed to in writing, shall any Contributor be
157 |       liable to You for damages, including any direct, indirect, special,
158 |       incidental, or consequential damages of any character arising as a
159 |       result of this License or out of the use or inability to use the
160 |       Work (including but not limited to damages for loss of goodwill,
161 |       work stoppage, computer failure or malfunction, or any and all
162 |       other commercial damages or losses), even if such Contributor
163 |       has been advised of the possibility of such damages.
164 | 
165 |    9. Accepting Warranty or Additional Liability. While redistributing
166 |       the Work or Derivative Works thereof, You may choose to offer,
167 |       and charge a fee for, acceptance of support, warranty, indemnity,
168 |       or other liability obligations and/or rights consistent with this
169 |       License. However, in accepting such obligations, You may act only
170 |       on Your own behalf and on Your sole responsibility, not on behalf
171 |       of any other Contributor, and only if You agree to indemnify,
172 |       defend, and hold each Contributor harmless for any liability
173 |       incurred by, or claims asserted against, such Contributor by reason
174 |       of your accepting any such warranty or additional liability.
175 | 
176 |    END OF TERMS AND CONDITIONS
177 | 
178 |    APPENDIX: How to apply the Apache License to your work.
179 | 
180 |       To apply the Apache License to your work, attach the following
181 |       boilerplate notice, with the fields enclosed by brackets "{}"
182 |       replaced with your own identifying information. (Don't include
183 |       the brackets!)  The text should be enclosed in the appropriate
184 |       comment syntax for the file format. We also recommend that a
185 |       file or class name and description of purpose be included on the
186 |       same "printed page" as the copyright notice for easier
187 |       identification within third-party archives.
188 | 
189 |    Copyright {yyyy} {name of copyright owner}
190 | 
191 |    Licensed under the Apache License, Version 2.0 (the "License");
192 |    you may not use this file except in compliance with the License.
193 |    You may obtain a copy of the License at
194 | 
195 |        http://www.apache.org/licenses/LICENSE-2.0
196 | 
197 |    Unless required by applicable law or agreed to in writing, software
198 |    distributed under the License is distributed on an "AS IS" BASIS,
199 |    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
200 |    See the License for the specific language governing permissions and
201 |    limitations under the License.
202 | 
203 | 


--------------------------------------------------------------------------------
/MANIFEST.in:
--------------------------------------------------------------------------------
 1 | include LICENSE
 2 | include *.rst
 3 | recursive-include samples *.py
 4 | recursive-include test *.py
 5 | 
 6 | recursive-include docs *.py
 7 | recursive-include docs *.rst
 8 | recursive-include docs Makefile
 9 | 
10 | 


--------------------------------------------------------------------------------
/README.rst:
--------------------------------------------------------------------------------
  1 | Matrix Client SDK for Python
  2 | ============================
  3 | 
  4 | .. image:: https://img.shields.io/pypi/v/matrix-client.svg?maxAge=600
  5 |   :target: https://pypi.python.org/pypi/matrix-client
  6 |   :alt: Latest Version
  7 | .. image:: https://travis-ci.org/matrix-org/matrix-python-sdk.svg?branch=master
  8 |   :target: https://travis-ci.org/matrix-org/matrix-python-sdk
  9 |   :alt: Travis-CI Results
 10 | .. image:: https://coveralls.io/repos/github/matrix-org/matrix-python-sdk/badge.svg?branch=master
 11 |   :target: https://coveralls.io/github/matrix-org/matrix-python-sdk?branch=master
 12 |   :alt: coveralls.io Results
 13 | .. image:: https://img.shields.io/matrix/matrix-python-sdk:matrix.org
 14 |    :target: https://matrix.to/#/%23matrix-python-sdk:matrix.org
 15 |    :alt: Matrix chatroom
 16 | .. image:: https://img.shields.io/badge/docs-stable-blue
 17 |    :target: https://matrix-org.github.io/matrix-python-sdk/
 18 |    :alt: Documentation
 19 | 
 20 | 
 21 | Matrix client-server SDK for Python 2.7 and 3.4+
 22 | 
 23 | Project Status
 24 | --------------
 25 | 
 26 | We strongly recommend using the `matrix-nio`_ library rather than this
 27 | sdk. It is both more featureful and more actively maintained.
 28 | 
 29 | This sdk is currently lightly maintained without any person ultimately
 30 | responsible for the project. Pull-requests **may** be reviewed, but no
 31 | new-features or bug-fixes are being actively developed. For more info
 32 | or to volunteer to help, please see
 33 | https://github.com/matrix-org/matrix-python-sdk/issues/279 or come
 34 | chat in `#matrix-python-sdk:matrix.org`_.
 35 | 
 36 | .. _`matrix-nio`: https://github.com/poljar/matrix-nio
 37 | .. _`#matrix-python-sdk:matrix.org`: https://matrix.to/#/%23matrix-python-sdk:matrix.org
 38 | 
 39 | Installation
 40 | ============
 41 | Stable release
 42 | --------------
 43 | Install with pip from pypi. This will install all necessary dependencies as well.
 44 | 
 45 | .. code:: shell
 46 | 
 47 |    pip install matrix_client
 48 | 
 49 | Development version
 50 | -------------------
 51 | Install using ``setup.py`` in root project directory. This will also install all
 52 | needed dependencies.
 53 | 
 54 | .. code:: shell
 55 | 
 56 |    git clone https://github.com/matrix-org/matrix-python-sdk.git
 57 |    cd matrix-python-sdk
 58 |    python setup.py install
 59 | 
 60 | Usage
 61 | =====
 62 | The SDK provides 2 layers of interaction. The low-level layer just wraps the
 63 | raw HTTP API calls. The high-level layer wraps the low-level layer and provides
 64 | an object model to perform actions on.
 65 | 
 66 | Client:
 67 | 
 68 | .. code:: python
 69 | 
 70 |     from matrix_client.client import MatrixClient
 71 | 
 72 |     client = MatrixClient("http://localhost:8008")
 73 | 
 74 |     # New user
 75 |     token = client.register_with_password(username="foobar", password="monkey")
 76 | 
 77 |     # Existing user
 78 |     token = client.login(username="foobar", password="monkey")
 79 | 
 80 |     room = client.create_room("my_room_alias")
 81 |     room.send_text("Hello!")
 82 | 
 83 | 
 84 | API:
 85 | 
 86 | .. code:: python
 87 | 
 88 |     from matrix_client.api import MatrixHttpApi
 89 | 
 90 |     matrix = MatrixHttpApi("https://matrix.org", token="some_token")
 91 |     response = matrix.send_message("!roomid:matrix.org", "Hello!")
 92 | 
 93 | 
 94 | Structure
 95 | =========
 96 | The SDK is split into two modules: ``api`` and ``client``.
 97 | 
 98 | API
 99 | ---
100 | This contains the raw HTTP API calls and has minimal business logic. You can
101 | set the access token (``token``) to use for requests as well as set a custom
102 | transaction ID (``txn_id``) which will be incremented for each request.
103 | 
104 | Client
105 | ------
106 | This encapsulates the API module and provides object models such as ``Room``.
107 | 
108 | Samples
109 | =======
110 | A collection of samples are included, written in Python 3.
111 | 
112 | You can either install the SDK, or run the sample like this:
113 | 
114 | .. code:: shell
115 | 
116 |     PYTHONPATH=. python samples/samplename.py
117 | 
118 | Building the Documentation
119 | ==========================
120 | 
121 | The documentation can be built by installing ``sphinx`` and ``sphinx_rtd_theme``.
122 | 
123 | Simple run ``make`` inside ``docs`` which will list the avaliable output formats.
124 | 


--------------------------------------------------------------------------------
/docs/Makefile:
--------------------------------------------------------------------------------
  1 | # Makefile for Sphinx documentation
  2 | #
  3 | 
  4 | # You can set these variables from the command line.
  5 | SPHINXOPTS    = 
  6 | SPHINXBUILD   = sphinx-build
  7 | PAPER         =
  8 | BUILDDIR      = build
  9 | 
 10 | # User-friendly check for sphinx-build
 11 | ifeq ($(shell which $(SPHINXBUILD) >/dev/null 2>&1; echo $?), 1)
 12 | $(error The '$(SPHINXBUILD)' command was not found. Make sure you have Sphinx installed, then set the SPHINXBUILD environment variable to point to the full path of the '$(SPHINXBUILD)' executable. Alternatively you can add the directory with the executable to your PATH. If you don\'t have Sphinx installed, grab it from http://sphinx-doc.org/)
 13 | endif
 14 | 
 15 | # Internal variables.
 16 | PAPEROPT_a4     = -D latex_paper_size=a4
 17 | PAPEROPT_letter = -D latex_paper_size=letter
 18 | ALLSPHINXOPTS   = -d $(BUILDDIR)/doctrees $(PAPEROPT_$(PAPER)) $(SPHINXOPTS) source
 19 | # the i18n builder cannot share the environment and doctrees with the others
 20 | I18NSPHINXOPTS  = $(PAPEROPT_$(PAPER)) $(SPHINXOPTS) source
 21 | 
 22 | .PHONY: help
 23 | help:
 24 | 	@echo "Please use \`make <target>' where <target> is one of"
 25 | 	@echo "  html       to make standalone HTML files"
 26 | 	@echo "  dirhtml    to make HTML files named index.html in directories"
 27 | 	@echo "  singlehtml to make a single large HTML file"
 28 | 	@echo "  pickle     to make pickle files"
 29 | 	@echo "  json       to make JSON files"
 30 | 	@echo "  htmlhelp   to make HTML files and a HTML help project"
 31 | 	@echo "  qthelp     to make HTML files and a qthelp project"
 32 | 	@echo "  applehelp  to make an Apple Help Book"
 33 | 	@echo "  devhelp    to make HTML files and a Devhelp project"
 34 | 	@echo "  epub       to make an epub"
 35 | 	@echo "  epub3      to make an epub3"
 36 | 	@echo "  latex      to make LaTeX files, you can set PAPER=a4 or PAPER=letter"
 37 | 	@echo "  latexpdf   to make LaTeX files and run them through pdflatex"
 38 | 	@echo "  latexpdfja to make LaTeX files and run them through platex/dvipdfmx"
 39 | 	@echo "  text       to make text files"
 40 | 	@echo "  man        to make manual pages"
 41 | 	@echo "  texinfo    to make Texinfo files"
 42 | 	@echo "  info       to make Texinfo files and run them through makeinfo"
 43 | 	@echo "  gettext    to make PO message catalogs"
 44 | 	@echo "  changes    to make an overview of all changed/added/deprecated items"
 45 | 	@echo "  xml        to make Docutils-native XML files"
 46 | 	@echo "  pseudoxml  to make pseudoxml-XML files for display purposes"
 47 | 	@echo "  linkcheck  to check all external links for integrity"
 48 | 	@echo "  doctest    to run all doctests embedded in the documentation (if enabled)"
 49 | 	@echo "  coverage   to run coverage check of the documentation (if enabled)"
 50 | 	@echo "  dummy      to check syntax errors of document sources"
 51 | 
 52 | .PHONY: clean
 53 | clean:
 54 | 	rm -rf $(BUILDDIR)/*
 55 | 
 56 | .PHONY: html
 57 | html:
 58 | 	$(SPHINXBUILD) -b html $(ALLSPHINXOPTS) $(BUILDDIR)/html
 59 | 	@echo
 60 | 	@echo "Build finished. The HTML pages are in $(BUILDDIR)/html."
 61 | 
 62 | .PHONY: dirhtml
 63 | dirhtml:
 64 | 	$(SPHINXBUILD) -b dirhtml $(ALLSPHINXOPTS) $(BUILDDIR)/dirhtml
 65 | 	@echo
 66 | 	@echo "Build finished. The HTML pages are in $(BUILDDIR)/dirhtml."
 67 | 
 68 | .PHONY: singlehtml
 69 | singlehtml:
 70 | 	$(SPHINXBUILD) -b singlehtml $(ALLSPHINXOPTS) $(BUILDDIR)/singlehtml
 71 | 	@echo
 72 | 	@echo "Build finished. The HTML page is in $(BUILDDIR)/singlehtml."
 73 | 
 74 | .PHONY: pickle
 75 | pickle:
 76 | 	$(SPHINXBUILD) -b pickle $(ALLSPHINXOPTS) $(BUILDDIR)/pickle
 77 | 	@echo
 78 | 	@echo "Build finished; now you can process the pickle files."
 79 | 
 80 | .PHONY: json
 81 | json:
 82 | 	$(SPHINXBUILD) -b json $(ALLSPHINXOPTS) $(BUILDDIR)/json
 83 | 	@echo
 84 | 	@echo "Build finished; now you can process the JSON files."
 85 | 
 86 | .PHONY: htmlhelp
 87 | htmlhelp:
 88 | 	$(SPHINXBUILD) -b htmlhelp $(ALLSPHINXOPTS) $(BUILDDIR)/htmlhelp
 89 | 	@echo
 90 | 	@echo "Build finished; now you can run HTML Help Workshop with the" \
 91 | 	      ".hhp project file in $(BUILDDIR)/htmlhelp."
 92 | 
 93 | .PHONY: qthelp
 94 | qthelp:
 95 | 	$(SPHINXBUILD) -b qthelp $(ALLSPHINXOPTS) $(BUILDDIR)/qthelp
 96 | 	@echo
 97 | 	@echo "Build finished; now you can run "qcollectiongenerator" with the" \
 98 | 	      ".qhcp project file in $(BUILDDIR)/qthelp, like this:"
 99 | 	@echo "# qcollectiongenerator $(BUILDDIR)/qthelp/MatrixPythonSDK.qhcp"
100 | 	@echo "To view the help file:"
101 | 	@echo "# assistant -collectionFile $(BUILDDIR)/qthelp/MatrixPythonSDK.qhc"
102 | 
103 | .PHONY: applehelp
104 | applehelp:
105 | 	$(SPHINXBUILD) -b applehelp $(ALLSPHINXOPTS) $(BUILDDIR)/applehelp
106 | 	@echo
107 | 	@echo "Build finished. The help book is in $(BUILDDIR)/applehelp."
108 | 	@echo "N.B. You won't be able to view it unless you put it in" \
109 | 	      "~/Library/Documentation/Help or install it in your application" \
110 | 	      "bundle."
111 | 
112 | .PHONY: devhelp
113 | devhelp:
114 | 	$(SPHINXBUILD) -b devhelp $(ALLSPHINXOPTS) $(BUILDDIR)/devhelp
115 | 	@echo
116 | 	@echo "Build finished."
117 | 	@echo "To view the help file:"
118 | 	@echo "# mkdir -p $HOME/.local/share/devhelp/MatrixPythonSDK"
119 | 	@echo "# ln -s $(BUILDDIR)/devhelp $HOME/.local/share/devhelp/MatrixPythonSDK"
120 | 	@echo "# devhelp"
121 | 
122 | .PHONY: epub
123 | epub:
124 | 	$(SPHINXBUILD) -b epub $(ALLSPHINXOPTS) $(BUILDDIR)/epub
125 | 	@echo
126 | 	@echo "Build finished. The epub file is in $(BUILDDIR)/epub."
127 | 
128 | .PHONY: epub3
129 | epub3:
130 | 	$(SPHINXBUILD) -b epub3 $(ALLSPHINXOPTS) $(BUILDDIR)/epub3
131 | 	@echo
132 | 	@echo "Build finished. The epub3 file is in $(BUILDDIR)/epub3."
133 | 
134 | .PHONY: latex
135 | latex:
136 | 	$(SPHINXBUILD) -b latex $(ALLSPHINXOPTS) $(BUILDDIR)/latex
137 | 	@echo
138 | 	@echo "Build finished; the LaTeX files are in $(BUILDDIR)/latex."
139 | 	@echo "Run \`make' in that directory to run these through (pdf)latex" \
140 | 	      "(use \`make latexpdf' here to do that automatically)."
141 | 
142 | .PHONY: latexpdf
143 | latexpdf:
144 | 	$(SPHINXBUILD) -b latex $(ALLSPHINXOPTS) $(BUILDDIR)/latex
145 | 	@echo "Running LaTeX files through pdflatex..."
146 | 	$(MAKE) -C $(BUILDDIR)/latex all-pdf
147 | 	@echo "pdflatex finished; the PDF files are in $(BUILDDIR)/latex."
148 | 
149 | .PHONY: latexpdfja
150 | latexpdfja:
151 | 	$(SPHINXBUILD) -b latex $(ALLSPHINXOPTS) $(BUILDDIR)/latex
152 | 	@echo "Running LaTeX files through platex and dvipdfmx..."
153 | 	$(MAKE) -C $(BUILDDIR)/latex all-pdf-ja
154 | 	@echo "pdflatex finished; the PDF files are in $(BUILDDIR)/latex."
155 | 
156 | .PHONY: text
157 | text:
158 | 	$(SPHINXBUILD) -b text $(ALLSPHINXOPTS) $(BUILDDIR)/text
159 | 	@echo
160 | 	@echo "Build finished. The text files are in $(BUILDDIR)/text."
161 | 
162 | .PHONY: man
163 | man:
164 | 	$(SPHINXBUILD) -b man $(ALLSPHINXOPTS) $(BUILDDIR)/man
165 | 	@echo
166 | 	@echo "Build finished. The manual pages are in $(BUILDDIR)/man."
167 | 
168 | .PHONY: texinfo
169 | texinfo:
170 | 	$(SPHINXBUILD) -b texinfo $(ALLSPHINXOPTS) $(BUILDDIR)/texinfo
171 | 	@echo
172 | 	@echo "Build finished. The Texinfo files are in $(BUILDDIR)/texinfo."
173 | 	@echo "Run \`make' in that directory to run these through makeinfo" \
174 | 	      "(use \`make info' here to do that automatically)."
175 | 
176 | .PHONY: info
177 | info:
178 | 	$(SPHINXBUILD) -b texinfo $(ALLSPHINXOPTS) $(BUILDDIR)/texinfo
179 | 	@echo "Running Texinfo files through makeinfo..."
180 | 	make -C $(BUILDDIR)/texinfo info
181 | 	@echo "makeinfo finished; the Info files are in $(BUILDDIR)/texinfo."
182 | 
183 | .PHONY: gettext
184 | gettext:
185 | 	$(SPHINXBUILD) -b gettext $(I18NSPHINXOPTS) $(BUILDDIR)/locale
186 | 	@echo
187 | 	@echo "Build finished. The message catalogs are in $(BUILDDIR)/locale."
188 | 
189 | .PHONY: changes
190 | changes:
191 | 	$(SPHINXBUILD) -b changes $(ALLSPHINXOPTS) $(BUILDDIR)/changes
192 | 	@echo
193 | 	@echo "The overview file is in $(BUILDDIR)/changes."
194 | 
195 | .PHONY: linkcheck
196 | linkcheck:
197 | 	$(SPHINXBUILD) -b linkcheck $(ALLSPHINXOPTS) $(BUILDDIR)/linkcheck
198 | 	@echo
199 | 	@echo "Link check complete; look for any errors in the above output " \
200 | 	      "or in $(BUILDDIR)/linkcheck/output.txt."
201 | 
202 | .PHONY: doctest
203 | doctest:
204 | 	$(SPHINXBUILD) -b doctest $(ALLSPHINXOPTS) $(BUILDDIR)/doctest
205 | 	@echo "Testing of doctests in the sources finished, look at the " \
206 | 	      "results in $(BUILDDIR)/doctest/output.txt."
207 | 
208 | .PHONY: coverage
209 | coverage:
210 | 	$(SPHINXBUILD) -b coverage $(ALLSPHINXOPTS) $(BUILDDIR)/coverage
211 | 	@echo "Testing of coverage in the sources finished, look at the " \
212 | 	      "results in $(BUILDDIR)/coverage/python.txt."
213 | 
214 | .PHONY: xml
215 | xml:
216 | 	$(SPHINXBUILD) -b xml $(ALLSPHINXOPTS) $(BUILDDIR)/xml
217 | 	@echo
218 | 	@echo "Build finished. The XML files are in $(BUILDDIR)/xml."
219 | 
220 | .PHONY: pseudoxml
221 | pseudoxml:
222 | 	$(SPHINXBUILD) -b pseudoxml $(ALLSPHINXOPTS) $(BUILDDIR)/pseudoxml
223 | 	@echo
224 | 	@echo "Build finished. The pseudo-XML files are in $(BUILDDIR)/pseudoxml."
225 | 
226 | .PHONY: dummy
227 | dummy:
228 | 	$(SPHINXBUILD) -b dummy $(ALLSPHINXOPTS) $(BUILDDIR)/dummy
229 | 	@echo
230 | 	@echo "Build finished. Dummy builder generates no files."
231 | 


--------------------------------------------------------------------------------
/docs/source/conf.py:
--------------------------------------------------------------------------------
  1 | #!/usr/bin/env python3
  2 | # -*- coding: utf-8 -*-
  3 | #
  4 | # Matrix Python SDK documentation build configuration file, created by
  5 | # sphinx-quickstart on Tue May  3 14:25:58 2016.
  6 | #
  7 | # This file is execfile()d with the current directory set to its
  8 | # containing dir.
  9 | #
 10 | # Note that not all possible configuration values are present in this
 11 | # autogenerated file.
 12 | #
 13 | # All configuration values have a default; values that are commented out
 14 | # serve to show the default.
 15 | 
 16 | import sys
 17 | import os
 18 | import sphinx_rtd_theme
 19 | 
 20 | 
 21 | srcdir = os.path.abspath('../../')
 22 | sys.path.insert(0, srcdir)
 23 | 
 24 | 
 25 | # If extensions (or modules to document with autodoc) are in another directory,
 26 | # add these directories to sys.path here. If the directory is relative to the
 27 | # documentation root, use os.path.abspath to make it absolute, like shown here.
 28 | # sys.path.insert(0, os.path.abspath('.'))
 29 | 
 30 | # -- General configuration ------------------------------------------------
 31 | 
 32 | # If your documentation needs a minimal Sphinx version, state it here.
 33 | needs_sphinx = '1.3'
 34 | 
 35 | # Add any Sphinx extension module names here, as strings. They can be
 36 | # extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
 37 | # ones.
 38 | extensions = [
 39 |     'sphinx.ext.viewcode',
 40 |     'sphinx.ext.autodoc',
 41 |     'sphinx.ext.napoleon'
 42 | ]
 43 | 
 44 | # Add any paths that contain templates here, relative to this directory.
 45 | templates_path = ['_templates']
 46 | 
 47 | # The suffix(es) of source filenames.
 48 | # You can specify multiple suffix as a list of string:
 49 | # source_suffix = ['.rst', '.md']
 50 | source_suffix = '.rst'
 51 | 
 52 | # The encoding of source files.
 53 | # source_encoding = 'utf-8-sig'
 54 | 
 55 | # The master toctree document.
 56 | master_doc = 'index'
 57 | 
 58 | # General information about the project.
 59 | project = 'Matrix Python SDK'
 60 | copyright = '2016, matrix.org'
 61 | author = 'matrix.org'
 62 | 
 63 | 
 64 | version = '0.4.0'
 65 | release = '0.4.0'
 66 | 
 67 | language = None
 68 | 
 69 | exclude_patterns = []
 70 | 
 71 | pygments_style = 'sphinx'
 72 | 
 73 | todo_include_todos = False
 74 | 
 75 | html_theme = "sphinx_rtd_theme"
 76 | html_theme_path = [sphinx_rtd_theme.get_html_theme_path()]
 77 | html_title = 'Matrix Python SDK v' + version
 78 | # html_static_path = ['_static']
 79 | 
 80 | htmlhelp_basename = 'MatrixPythonSDKdoc'
 81 | highlight_language = 'python'
 82 | 
 83 | latex_documents = [
 84 |     (master_doc, 'MatrixPythonSDK.tex', 'Matrix Python SDK Documentation',
 85 |      'matrix.org', 'manual'),
 86 | ]
 87 | 
 88 | man_pages = [
 89 |     (master_doc, 'matrixpythonsdk', 'Matrix Python SDK Documentation',
 90 |      [author], 1)
 91 | ]
 92 | 
 93 | texinfo_documents = [
 94 |     (master_doc, 'MatrixPythonSDK', 'Matrix Python SDK Documentation',
 95 |      author, 'MatrixPythonSDK', 'SDK for writing Matrix Clients in Python',
 96 |      'Miscellaneous'),
 97 | ]
 98 | 
 99 | autodoc_mock_imports = ["olm", "canonicaljson"]
100 | 


--------------------------------------------------------------------------------
/docs/source/index.rst:
--------------------------------------------------------------------------------
 1 | .. Matrix Python SDK documentation master file, created by
 2 |    sphinx-quickstart on Tue May  3 14:25:58 2016.
 3 |    You can adapt this file completely to your liking, but it should at least
 4 |    contain the root `toctree` directive.
 5 | 
 6 | Welcome to Matrix Python SDK's documentation!
 7 | =============================================
 8 | 
 9 | Contents:
10 | 
11 | .. toctree::
12 |    :maxdepth: 2
13 | 
14 |    matrix_client
15 | 
16 | 
17 | Indices and tables
18 | ==================
19 | 
20 | * :ref:`genindex`
21 | * :ref:`modindex`
22 | * :ref:`search`
23 | 
24 | 


--------------------------------------------------------------------------------
/docs/source/matrix_client.rst:
--------------------------------------------------------------------------------
 1 | matrix_client package
 2 | =====================
 3 | 
 4 | matrix_client.client
 5 | ---------------------------
 6 | 
 7 | .. automodule:: matrix_client.client
 8 |     :members:
 9 |     :undoc-members:
10 |     :show-inheritance:
11 | 
12 | matrix_client.api
13 | ------------------------
14 | 
15 | .. automodule:: matrix_client.api
16 |     :members:
17 |     :undoc-members:
18 |     :show-inheritance:
19 | 
20 | matrix_client.user
21 | ------------------------
22 | 
23 | .. automodule:: matrix_client.user
24 |     :members:
25 |     :undoc-members:
26 |     :show-inheritance:
27 | 
28 | matrix_client.room
29 | ------------------------
30 | 
31 | .. automodule:: matrix_client.room
32 |     :members:
33 |     :undoc-members:
34 |     :show-inheritance:
35 | 
36 | matrix_client.checks
37 | ------------------------
38 | 
39 | .. automodule:: matrix_client.checks
40 |     :members:
41 |     :undoc-members:
42 |     :show-inheritance:
43 | 
44 | matrix_client.errors
45 | ------------------------
46 | 
47 | .. automodule:: matrix_client.errors
48 |     :members:
49 |     :undoc-members:
50 |     :show-inheritance:
51 | 
52 | matrix_client.crypto
53 | ------------------------
54 | 
55 | .. automodule:: matrix_client.crypto.olm_device
56 |     :members:
57 |     :undoc-members:
58 |     :show-inheritance:
59 | 


--------------------------------------------------------------------------------
/matrix_client/__init__.py:
--------------------------------------------------------------------------------
 1 | # -*- coding: utf-8 -*-
 2 | # Copyright 2015 OpenMarket Ltd
 3 | # Copyright 2018 Adam Beckmeyer
 4 | #
 5 | # Licensed under the Apache License, Version 2.0 (the "License");
 6 | # you may not use this file except in compliance with the License.
 7 | # You may obtain a copy of the License at
 8 | #
 9 | #     http://www.apache.org/licenses/LICENSE-2.0
10 | #
11 | # Unless required by applicable law or agreed to in writing, software
12 | # distributed under the License is distributed on an "AS IS" BASIS,
13 | # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
14 | # See the License for the specific language governing permissions and
15 | # limitations under the License.
16 | __version__ = "0.4.0"
17 | 


--------------------------------------------------------------------------------
/matrix_client/api.py:
--------------------------------------------------------------------------------
   1 | # -*- coding: utf-8 -*-
   2 | # Copyright 2015 OpenMarket Ltd
   3 | # Copyright 2017, 2018 Adam Beckmeyer
   4 | #
   5 | # Licensed under the Apache License, Version 2.0 (the "License");
   6 | # you may not use this file except in compliance with the License.
   7 | # You may obtain a copy of the License at
   8 | #
   9 | #     http://www.apache.org/licenses/LICENSE-2.0
  10 | #
  11 | # Unless required by applicable law or agreed to in writing, software
  12 | # distributed under the License is distributed on an "AS IS" BASIS,
  13 | # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  14 | # See the License for the specific language governing permissions and
  15 | # limitations under the License.
  16 | 
  17 | import json
  18 | import warnings
  19 | from requests import Session, RequestException
  20 | from time import time, sleep
  21 | from .__init__ import __version__
  22 | from .errors import MatrixError, MatrixRequestError, MatrixHttpLibError
  23 | from urllib3.util import parse_url
  24 | from urllib3.exceptions import LocationParseError
  25 | 
  26 | try:
  27 |     from urllib import quote
  28 | except ImportError:
  29 |     from urllib.parse import quote
  30 | 
  31 | MATRIX_V2_API_PATH = "/_matrix/client/r0"
  32 | 
  33 | 
  34 | class MatrixHttpApi(object):
  35 |     """Contains all raw Matrix HTTP Client-Server API calls.
  36 | 
  37 |     For room and sync handling, consider using MatrixClient.
  38 | 
  39 |     Args:
  40 |         base_url (str): The home server URL e.g. 'http://localhost:8008'
  41 |         token (str): Optional. The client's access token.
  42 |         identity (str): Optional. The mxid to act as (For application services only).
  43 |         default_429_wait_ms (int): Optional. Time in millseconds to wait before retrying
  44 |                                              a request when server returns a HTTP 429
  45 |                                              response without a 'retry_after_ms' key.
  46 |         use_authorization_header (bool): Optional. Use Authorization header instead
  47 |                 `                        of access_token query parameter.
  48 | 
  49 |     Examples:
  50 |         Create a client and send a message::
  51 | 
  52 |             matrix = MatrixHttpApi("https://matrix.org", token="foobar")
  53 |             response = matrix.sync()
  54 |             response = matrix.send_message("!roomid:matrix.org", "Hello!")
  55 |     """
  56 | 
  57 |     def __init__(
  58 |             self, base_url, token=None, identity=None,
  59 |             default_429_wait_ms=5000,
  60 |             use_authorization_header=True
  61 |     ):
  62 |         try:
  63 |             scheme, auth, host, port, path, query, fragment = parse_url(base_url)
  64 |         except LocationParseError:
  65 |             raise MatrixError("Invalid homeserver url %s" % base_url)
  66 |         if not scheme:
  67 |             raise MatrixError("No scheme in homeserver url %s" % base_url)
  68 |         self._base_url = base_url
  69 | 
  70 |         self.token = token
  71 |         self.identity = identity
  72 |         self.txn_id = 0
  73 |         self.validate_cert = True
  74 |         self.session = Session()
  75 |         self.default_429_wait_ms = default_429_wait_ms
  76 |         self.use_authorization_header = use_authorization_header
  77 | 
  78 |     def initial_sync(self, limit=1):
  79 |         """
  80 |         .. warning::
  81 | 
  82 |             Deprecated. Use sync instead.
  83 | 
  84 |         Perform /initialSync.
  85 | 
  86 |         Args:
  87 |             limit (int): The limit= param to provide.
  88 |         """
  89 |         warnings.warn("initial_sync is deprecated. Use sync instead.", DeprecationWarning)
  90 |         return self._send("GET", "/initialSync", query_params={"limit": limit})
  91 | 
  92 |     def sync(self, since=None, timeout_ms=30000, filter=None,
  93 |              full_state=None, set_presence=None):
  94 |         """ Perform a sync request.
  95 | 
  96 |         Args:
  97 |             since (str): Optional. A token which specifies where to continue a sync from.
  98 |             timeout_ms (int): Optional. The time in milliseconds to wait.
  99 |             filter (int|str): Either a Filter ID or a JSON string.
 100 |             full_state (bool): Return the full state for every room the user has joined
 101 |                 Defaults to false.
 102 |             set_presence (str): Should the client be marked as "online" or" offline"
 103 |         """
 104 | 
 105 |         request = {
 106 |             # non-integer timeouts appear to cause issues
 107 |             "timeout": int(timeout_ms)
 108 |         }
 109 | 
 110 |         if since:
 111 |             request["since"] = since
 112 | 
 113 |         if filter:
 114 |             request["filter"] = filter
 115 | 
 116 |         if full_state:
 117 |             request["full_state"] = json.dumps(full_state)
 118 | 
 119 |         if set_presence:
 120 |             request["set_presence"] = set_presence
 121 | 
 122 |         return self._send("GET", "/sync", query_params=request,
 123 |                           api_path=MATRIX_V2_API_PATH)
 124 | 
 125 |     def validate_certificate(self, valid):
 126 |         self.validate_cert = valid
 127 | 
 128 |     def register(self, auth_body=None, kind="user", bind_email=None,
 129 |                  username=None, password=None, device_id=None,
 130 |                  initial_device_display_name=None, inhibit_login=None):
 131 |         """Performs /register.
 132 | 
 133 |         Args:
 134 |             auth_body (dict): Authentication Params.
 135 |             kind (str): Specify kind of account to register. Can be 'guest' or 'user'.
 136 |             bind_email (bool): Whether to use email in registration and authentication.
 137 |             username (str): The localpart of a Matrix ID.
 138 |             password (str): The desired password of the account.
 139 |             device_id (str): ID of the client device.
 140 |             initial_device_display_name (str): Display name to be assigned.
 141 |             inhibit_login (bool): Whether to login after registration. Defaults to false.
 142 |         """
 143 |         content = {}
 144 |         content["kind"] = kind
 145 |         if auth_body:
 146 |             content["auth"] = auth_body
 147 |         if username:
 148 |             content["username"] = username
 149 |         if password:
 150 |             content["password"] = password
 151 |         if device_id:
 152 |             content["device_id"] = device_id
 153 |         if initial_device_display_name:
 154 |             content["initial_device_display_name"] = \
 155 |                     initial_device_display_name
 156 |         if bind_email:
 157 |             content["bind_email"] = bind_email
 158 |         if inhibit_login:
 159 |             content["inhibit_login"] = inhibit_login
 160 |         return self._send(
 161 |             "POST",
 162 |             "/register",
 163 |             content=content,
 164 |             query_params={'kind': kind}
 165 |         )
 166 | 
 167 |     def login(self, login_type, **kwargs):
 168 |         """Perform /login.
 169 | 
 170 |         Args:
 171 |             login_type (str): The value for the 'type' key.
 172 |             **kwargs: Additional key/values to add to the JSON submitted.
 173 |         """
 174 |         content = {
 175 |             "type": login_type
 176 |         }
 177 |         for key in kwargs:
 178 |             if kwargs[key]:
 179 |                 content[key] = kwargs[key]
 180 | 
 181 |         return self._send("POST", "/login", content)
 182 | 
 183 |     def logout(self):
 184 |         """Perform /logout.
 185 |         """
 186 |         return self._send("POST", "/logout")
 187 | 
 188 |     def logout_all(self):
 189 |         """Perform /logout/all."""
 190 |         return self._send("POST", "/logout/all")
 191 | 
 192 |     def create_room(
 193 |                 self,
 194 |                 alias=None,
 195 |                 name=None,
 196 |                 is_public=False,
 197 |                 invitees=None,
 198 |                 federate=None
 199 |             ):
 200 |         """Perform /createRoom.
 201 | 
 202 |         Args:
 203 |             alias (str): Optional. The room alias name to set for this room.
 204 |             name (str): Optional. Name for new room.
 205 |             is_public (bool): Optional. The public/private visibility.
 206 |             invitees (list<str>): Optional. The list of user IDs to invite.
 207 |             federate (bool): Optional. Сan a room be federated.
 208 |                 Default to True.
 209 |         """
 210 |         content = {
 211 |             "visibility": "public" if is_public else "private"
 212 |         }
 213 |         if alias:
 214 |             content["room_alias_name"] = alias
 215 |         if invitees:
 216 |             content["invite"] = invitees
 217 |         if name:
 218 |             content["name"] = name
 219 |         if federate is not None:
 220 |             content["creation_content"] = {'m.federate': federate}
 221 |         return self._send("POST", "/createRoom", content)
 222 | 
 223 |     def join_room(self, room_id_or_alias):
 224 |         """Performs /join/$room_id
 225 | 
 226 |         Args:
 227 |             room_id_or_alias (str): The room ID or room alias to join.
 228 |         """
 229 |         if not room_id_or_alias:
 230 |             raise MatrixError("No alias or room ID to join.")
 231 | 
 232 |         path = "/join/%s" % quote(room_id_or_alias)
 233 | 
 234 |         return self._send("POST", path)
 235 | 
 236 |     def event_stream(self, from_token, timeout=30000):
 237 |         """ Deprecated. Use sync instead.
 238 |         Performs /events
 239 | 
 240 |         Args:
 241 |             from_token (str): The 'from' query parameter.
 242 |             timeout (int): Optional. The 'timeout' query parameter.
 243 |         """
 244 |         warnings.warn("event_stream is deprecated. Use sync instead.",
 245 |                       DeprecationWarning)
 246 |         path = "/events"
 247 |         return self._send(
 248 |             "GET", path, query_params={
 249 |                 "timeout": timeout,
 250 |                 "from": from_token
 251 |             }
 252 |         )
 253 | 
 254 |     def send_state_event(self, room_id, event_type, content, state_key="",
 255 |                          timestamp=None):
 256 |         """Perform PUT /rooms/$room_id/state/$event_type
 257 | 
 258 |         Args:
 259 |             room_id(str): The room ID to send the state event in.
 260 |             event_type(str): The state event type to send.
 261 |             content(dict): The JSON content to send.
 262 |             state_key(str): Optional. The state key for the event.
 263 |             timestamp (int): Set origin_server_ts (For application services only)
 264 |         """
 265 |         path = "/rooms/%s/state/%s" % (
 266 |             quote(room_id), quote(event_type),
 267 |         )
 268 |         if state_key:
 269 |             path += "/%s" % (quote(state_key))
 270 |         params = {}
 271 |         if timestamp:
 272 |             params["ts"] = timestamp
 273 |         return self._send("PUT", path, content, query_params=params)
 274 | 
 275 |     def get_state_event(self, room_id, event_type):
 276 |         """Perform GET /rooms/$room_id/state/$event_type
 277 | 
 278 |         Args:
 279 |             room_id(str): The room ID.
 280 |             event_type (str): The type of the event.
 281 | 
 282 |         Raises:
 283 |             MatrixRequestError(code=404) if the state event is not found.
 284 |         """
 285 |         return self._send("GET", "/rooms/{}/state/{}".format(quote(room_id), event_type))
 286 | 
 287 |     def send_message_event(self, room_id, event_type, content, txn_id=None,
 288 |                            timestamp=None):
 289 |         """Perform PUT /rooms/$room_id/send/$event_type
 290 | 
 291 |         Args:
 292 |             room_id (str): The room ID to send the message event in.
 293 |             event_type (str): The event type to send.
 294 |             content (dict): The JSON content to send.
 295 |             txn_id (int): Optional. The transaction ID to use.
 296 |             timestamp (int): Set origin_server_ts (For application services only)
 297 |         """
 298 |         if not txn_id:
 299 |             txn_id = self._make_txn_id()
 300 | 
 301 |         path = "/rooms/%s/send/%s/%s" % (
 302 |             quote(room_id), quote(event_type), quote(str(txn_id)),
 303 |         )
 304 |         params = {}
 305 |         if timestamp:
 306 |             params["ts"] = timestamp
 307 |         return self._send("PUT", path, content, query_params=params)
 308 | 
 309 |     def redact_event(self, room_id, event_id, reason=None, txn_id=None, timestamp=None):
 310 |         """Perform PUT /rooms/$room_id/redact/$event_id/$txn_id/
 311 | 
 312 |         Args:
 313 |             room_id(str): The room ID to redact the message event in.
 314 |             event_id(str): The event id to redact.
 315 |             reason (str): Optional. The reason the message was redacted.
 316 |             txn_id(int): Optional. The transaction ID to use.
 317 |             timestamp(int): Optional. Set origin_server_ts (For application services only)
 318 |         """
 319 |         if not txn_id:
 320 |             txn_id = self._make_txn_id()
 321 | 
 322 |         path = '/rooms/%s/redact/%s/%s' % (
 323 |             room_id, event_id, txn_id
 324 |         )
 325 |         content = {}
 326 |         if reason:
 327 |             content['reason'] = reason
 328 |         params = {}
 329 |         if timestamp:
 330 |             params["ts"] = timestamp
 331 |         return self._send("PUT", path, content, query_params=params)
 332 | 
 333 |     # content_type can be a image,audio or video
 334 |     # extra information should be supplied, see
 335 |     # https://matrix.org/docs/spec/r0.0.1/client_server.html
 336 |     def send_content(self, room_id, item_url, item_name, msg_type,
 337 |                      extra_information=None, timestamp=None):
 338 |         if extra_information is None:
 339 |             extra_information = {}
 340 | 
 341 |         content_pack = {
 342 |             "url": item_url,
 343 |             "msgtype": msg_type,
 344 |             "body": item_name,
 345 |             "info": extra_information
 346 |         }
 347 |         return self.send_message_event(room_id, "m.room.message", content_pack,
 348 |                                        timestamp=timestamp)
 349 | 
 350 |     # http://matrix.org/docs/spec/client_server/r0.2.0.html#m-location
 351 |     def send_location(self, room_id, geo_uri, name, thumb_url=None, thumb_info=None,
 352 |                       timestamp=None):
 353 |         """Send m.location message event
 354 | 
 355 |         Args:
 356 |             room_id (str): The room ID to send the event in.
 357 |             geo_uri (str): The geo uri representing the location.
 358 |             name (str): Description for the location.
 359 |             thumb_url (str): URL to the thumbnail of the location.
 360 |             thumb_info (dict): Metadata about the thumbnail, type ImageInfo.
 361 |             timestamp (int): Set origin_server_ts (For application services only)
 362 |         """
 363 |         content_pack = {
 364 |             "geo_uri": geo_uri,
 365 |             "msgtype": "m.location",
 366 |             "body": name,
 367 |         }
 368 |         if thumb_url:
 369 |             content_pack["thumbnail_url"] = thumb_url
 370 |         if thumb_info:
 371 |             content_pack["thumbnail_info"] = thumb_info
 372 | 
 373 |         return self.send_message_event(room_id, "m.room.message", content_pack,
 374 |                                        timestamp=timestamp)
 375 | 
 376 |     def send_message(self, room_id, text_content, msgtype="m.text", timestamp=None):
 377 |         """Perform PUT /rooms/$room_id/send/m.room.message
 378 | 
 379 |         Args:
 380 |             room_id (str): The room ID to send the event in.
 381 |             text_content (str): The m.text body to send.
 382 |             timestamp (int): Set origin_server_ts (For application services only)
 383 |         """
 384 |         return self.send_message_event(
 385 |             room_id, "m.room.message",
 386 |             self.get_text_body(text_content, msgtype),
 387 |             timestamp=timestamp
 388 |         )
 389 | 
 390 |     def send_emote(self, room_id, text_content, timestamp=None):
 391 |         """Perform PUT /rooms/$room_id/send/m.room.message with m.emote msgtype
 392 | 
 393 |         Args:
 394 |             room_id (str): The room ID to send the event in.
 395 |             text_content (str): The m.emote body to send.
 396 |             timestamp (int): Set origin_server_ts (For application services only)
 397 |         """
 398 |         return self.send_message_event(
 399 |             room_id, "m.room.message",
 400 |             self.get_emote_body(text_content),
 401 |             timestamp=timestamp
 402 |         )
 403 | 
 404 |     def send_notice(self, room_id, text_content, timestamp=None):
 405 |         """Perform PUT /rooms/$room_id/send/m.room.message with m.notice msgtype
 406 | 
 407 |         Args:
 408 |             room_id (str): The room ID to send the event in.
 409 |             text_content (str): The m.notice body to send.
 410 |             timestamp (int): Set origin_server_ts (For application services only)
 411 |         """
 412 |         body = {
 413 |             "msgtype": "m.notice",
 414 |             "body": text_content
 415 |         }
 416 |         return self.send_message_event(room_id, "m.room.message", body,
 417 |                                        timestamp=timestamp)
 418 | 
 419 |     def get_room_messages(self, room_id, token, direction, limit=10, to=None):
 420 |         """Perform GET /rooms/{roomId}/messages.
 421 | 
 422 |         Args:
 423 |             room_id (str): The room's id.
 424 |             token (str): The token to start returning events from.
 425 |             direction (str):  The direction to return events from. One of: ["b", "f"].
 426 |             limit (int): The maximum number of events to return.
 427 |             to (str): The token to stop returning events at.
 428 |         """
 429 |         query = {
 430 |             "roomId": room_id,
 431 |             "from": token,
 432 |             "dir": direction,
 433 |             "limit": limit,
 434 |         }
 435 | 
 436 |         if to:
 437 |             query["to"] = to
 438 | 
 439 |         return self._send("GET", "/rooms/{}/messages".format(quote(room_id)),
 440 |                           query_params=query, api_path="/_matrix/client/r0")
 441 | 
 442 |     def get_room_name(self, room_id):
 443 |         """Perform GET /rooms/$room_id/state/m.room.name
 444 |         Args:
 445 |             room_id(str): The room ID
 446 |         """
 447 |         return self.get_state_event(room_id, "m.room.name")
 448 | 
 449 |     def set_room_name(self, room_id, name, timestamp=None):
 450 |         """Perform PUT /rooms/$room_id/state/m.room.name
 451 |         Args:
 452 |             room_id (str): The room ID
 453 |             name (str): The new room name
 454 |             timestamp (int): Set origin_server_ts (For application services only)
 455 |         """
 456 |         body = {
 457 |             "name": name
 458 |         }
 459 |         return self.send_state_event(room_id, "m.room.name", body, timestamp=timestamp)
 460 | 
 461 |     def get_room_topic(self, room_id):
 462 |         """Perform GET /rooms/$room_id/state/m.room.topic
 463 |         Args:
 464 |             room_id (str): The room ID
 465 |         """
 466 |         return self.get_state_event(room_id, "m.room.topic")
 467 | 
 468 |     def set_room_topic(self, room_id, topic, timestamp=None):
 469 |         """Perform PUT /rooms/$room_id/state/m.room.topic
 470 |         Args:
 471 |             room_id (str): The room ID
 472 |             topic (str): The new room topic
 473 |             timestamp (int): Set origin_server_ts (For application services only)
 474 |         """
 475 |         body = {
 476 |             "topic": topic
 477 |         }
 478 |         return self.send_state_event(room_id, "m.room.topic", body, timestamp=timestamp)
 479 | 
 480 |     def get_power_levels(self, room_id):
 481 |         """Perform GET /rooms/$room_id/state/m.room.power_levels
 482 | 
 483 |         Args:
 484 |             room_id(str): The room ID
 485 |         """
 486 |         return self.get_state_event(room_id, "m.room.power_levels")
 487 | 
 488 |     def set_power_levels(self, room_id, content):
 489 |         """Perform PUT /rooms/$room_id/state/m.room.power_levels
 490 | 
 491 |         Note that any power levels which are not explicitly specified
 492 |         in the content arg are reset to default values.
 493 | 
 494 |         Args:
 495 |             room_id (str): The room ID
 496 |             content (dict): The JSON content to send. See example content below.
 497 | 
 498 |         Example::
 499 | 
 500 |             api = MatrixHttpApi("http://example.com", token="foobar")
 501 |             api.set_power_levels("!exampleroom:example.com",
 502 |                 {
 503 |                     "ban": 50, # defaults to 50 if unspecified
 504 |                     "events": {
 505 |                         "m.room.name": 100, # must have PL 100 to change room name
 506 |                         "m.room.power_levels": 100 # must have PL 100 to change PLs
 507 |                     },
 508 |                     "events_default": 0, # defaults to 0
 509 |                     "invite": 50, # defaults to 50
 510 |                     "kick": 50, # defaults to 50
 511 |                     "redact": 50, # defaults to 50
 512 |                     "state_default": 50, # defaults to 50 if m.room.power_levels exists
 513 |                     "users": {
 514 |                         "@someguy:example.com": 100 # defaults to 0
 515 |                     },
 516 |                     "users_default": 0 # defaults to 0
 517 |                 }
 518 |             )
 519 |         """
 520 |         # Synapse returns M_UNKNOWN if body['events'] is omitted,
 521 |         #  as of 2016-10-31
 522 |         if "events" not in content:
 523 |             content["events"] = {}
 524 | 
 525 |         return self.send_state_event(room_id, "m.room.power_levels", content)
 526 | 
 527 |     def leave_room(self, room_id):
 528 |         """Perform POST /rooms/$room_id/leave
 529 | 
 530 |         Args:
 531 |             room_id (str): The room ID
 532 |         """
 533 |         return self._send("POST", "/rooms/" + room_id + "/leave", {})
 534 | 
 535 |     def forget_room(self, room_id):
 536 |         """Perform POST /rooms/$room_id/forget
 537 | 
 538 |         Args:
 539 |             room_id(str): The room ID
 540 |         """
 541 |         return self._send("POST", "/rooms/" + room_id + "/forget", content={})
 542 | 
 543 |     def invite_user(self, room_id, user_id):
 544 |         """Perform POST /rooms/$room_id/invite
 545 | 
 546 |         Args:
 547 |             room_id (str): The room ID
 548 |             user_id (str): The user ID of the invitee
 549 |         """
 550 |         body = {
 551 |             "user_id": user_id
 552 |         }
 553 |         return self._send("POST", "/rooms/" + room_id + "/invite", body)
 554 | 
 555 |     def kick_user(self, room_id, user_id, reason=""):
 556 |         """Calls set_membership with membership="leave" for the user_id provided
 557 |         """
 558 |         self.set_membership(room_id, user_id, "leave", reason)
 559 | 
 560 |     def get_membership(self, room_id, user_id):
 561 |         """Perform GET /rooms/$room_id/state/m.room.member/$user_id
 562 | 
 563 |         Args:
 564 |             room_id (str): The room ID
 565 |             user_id (str): The user ID
 566 |         """
 567 |         return self._send(
 568 |             "GET",
 569 |             "/rooms/%s/state/m.room.member/%s" % (room_id, user_id)
 570 |         )
 571 | 
 572 |     def set_membership(self, room_id, user_id, membership, reason="", profile=None,
 573 |                        timestamp=None):
 574 |         """Perform PUT /rooms/$room_id/state/m.room.member/$user_id
 575 | 
 576 |         Args:
 577 |             room_id (str): The room ID
 578 |             user_id (str): The user ID
 579 |             membership (str): New membership value
 580 |             reason (str): The reason
 581 |             timestamp (int): Set origin_server_ts (For application services only)
 582 |         """
 583 |         if profile is None:
 584 |             profile = {}
 585 |         body = {
 586 |             "membership": membership,
 587 |             "reason": reason
 588 |         }
 589 |         if 'displayname' in profile:
 590 |             body["displayname"] = profile["displayname"]
 591 |         if 'avatar_url' in profile:
 592 |             body["avatar_url"] = profile["avatar_url"]
 593 | 
 594 |         return self.send_state_event(room_id, "m.room.member", body, state_key=user_id,
 595 |                                      timestamp=timestamp)
 596 | 
 597 |     def ban_user(self, room_id, user_id, reason=""):
 598 |         """Perform POST /rooms/$room_id/ban
 599 | 
 600 |         Args:
 601 |             room_id (str): The room ID
 602 |             user_id (str): The user ID of the banee(sic)
 603 |             reason (str): The reason for this ban
 604 |         """
 605 |         body = {
 606 |             "user_id": user_id,
 607 |             "reason": reason
 608 |         }
 609 |         return self._send("POST", "/rooms/" + room_id + "/ban", body)
 610 | 
 611 |     def unban_user(self, room_id, user_id):
 612 |         """Perform POST /rooms/$room_id/unban
 613 | 
 614 |         Args:
 615 |             room_id (str): The room ID
 616 |             user_id (str): The user ID of the banee(sic)
 617 |         """
 618 |         body = {
 619 |             "user_id": user_id
 620 |         }
 621 |         return self._send("POST", "/rooms/" + room_id + "/unban", body)
 622 | 
 623 |     def get_user_tags(self, user_id, room_id):
 624 |         return self._send(
 625 |             "GET",
 626 |             "/user/%s/rooms/%s/tags" % (user_id, room_id),
 627 |         )
 628 | 
 629 |     def remove_user_tag(self, user_id, room_id, tag):
 630 |         return self._send(
 631 |             "DELETE",
 632 |             "/user/%s/rooms/%s/tags/%s" % (user_id, room_id, tag),
 633 |         )
 634 | 
 635 |     def add_user_tag(self, user_id, room_id, tag, order=None, body=None):
 636 |         if body:
 637 |             pass
 638 |         elif order:
 639 |             body = {"order": order}
 640 |         else:
 641 |             body = {}
 642 |         return self._send(
 643 |             "PUT",
 644 |             "/user/%s/rooms/%s/tags/%s" % (user_id, room_id, tag),
 645 |             body,
 646 |         )
 647 | 
 648 |     def set_account_data(self, user_id, type, account_data):
 649 |         return self._send(
 650 |             "PUT",
 651 |             "/user/%s/account_data/%s" % (user_id, type),
 652 |             account_data,
 653 |         )
 654 | 
 655 |     def set_room_account_data(self, user_id, room_id, type, account_data):
 656 |         return self._send(
 657 |             "PUT",
 658 |             "/user/%s/rooms/%s/account_data/%s" % (user_id, room_id, type),
 659 |             account_data
 660 |         )
 661 | 
 662 |     def get_room_state(self, room_id):
 663 |         """Perform GET /rooms/$room_id/state
 664 | 
 665 |         Args:
 666 |             room_id (str): The room ID
 667 |         """
 668 |         return self._send("GET", "/rooms/" + room_id + "/state")
 669 | 
 670 |     def get_text_body(self, text, msgtype="m.text"):
 671 |         return {
 672 |             "msgtype": msgtype,
 673 |             "body": text
 674 |         }
 675 | 
 676 |     def get_emote_body(self, text):
 677 |         return {
 678 |             "msgtype": "m.emote",
 679 |             "body": text
 680 |         }
 681 | 
 682 |     def get_filter(self, user_id, filter_id):
 683 |         return self._send("GET", "/user/{userId}/filter/{filterId}"
 684 |                           .format(userId=user_id, filterId=filter_id))
 685 | 
 686 |     def create_filter(self, user_id, filter_params):
 687 |         return self._send("POST",
 688 |                           "/user/{userId}/filter".format(userId=user_id),
 689 |                           filter_params)
 690 | 
 691 |     def _send(self, method, path, content=None, query_params=None, headers=None,
 692 |               api_path=MATRIX_V2_API_PATH, return_json=True):
 693 |         if query_params is None:
 694 |             query_params = {}
 695 |         if headers is None:
 696 |             headers = {}
 697 | 
 698 |         if "User-Agent" not in headers:
 699 |             headers["User-Agent"] = "matrix-python-sdk/%s" % __version__
 700 | 
 701 |         method = method.upper()
 702 |         if method not in ["GET", "PUT", "DELETE", "POST"]:
 703 |             raise MatrixError("Unsupported HTTP method: %s" % method)
 704 | 
 705 |         if "Content-Type" not in headers:
 706 |             headers["Content-Type"] = "application/json"
 707 | 
 708 |         if self.use_authorization_header:
 709 |             headers["Authorization"] = 'Bearer %s' % self.token
 710 |         else:
 711 |             query_params["access_token"] = self.token
 712 | 
 713 |         if self.identity:
 714 |             query_params["user_id"] = self.identity
 715 | 
 716 |         endpoint = self._base_url + api_path + path
 717 | 
 718 |         if headers["Content-Type"] == "application/json" and content is not None:
 719 |             content = json.dumps(content)
 720 | 
 721 |         while True:
 722 |             try:
 723 |                 response = self.session.request(
 724 |                     method, endpoint,
 725 |                     params=query_params,
 726 |                     data=content,
 727 |                     headers=headers,
 728 |                     verify=self.validate_cert
 729 |                 )
 730 |             except RequestException as e:
 731 |                 raise MatrixHttpLibError(e, method, endpoint)
 732 | 
 733 |             if response.status_code == 429:
 734 |                 waittime = self.default_429_wait_ms / 1000
 735 |                 try:
 736 |                     waittime = response.json()['retry_after_ms'] / 1000
 737 |                 except KeyError:
 738 |                     try:
 739 |                         errordata = json.loads(response.json()['error'])
 740 |                         waittime = errordata['retry_after_ms'] / 1000
 741 |                     except KeyError:
 742 |                         pass
 743 |                 sleep(waittime)
 744 |             else:
 745 |                 break
 746 | 
 747 |         if response.status_code < 200 or response.status_code >= 300:
 748 |             raise MatrixRequestError(
 749 |                 code=response.status_code, content=response.text
 750 |             )
 751 |         if return_json:
 752 |             return response.json()
 753 |         else:
 754 |             return response
 755 | 
 756 |     def media_upload(self, content, content_type, filename=None):
 757 |         query_params = {}
 758 |         if filename is not None:
 759 |             query_params['filename'] = filename
 760 | 
 761 |         return self._send(
 762 |             "POST", "",
 763 |             content=content,
 764 |             headers={"Content-Type": content_type},
 765 |             api_path="/_matrix/media/r0/upload",
 766 |             query_params=query_params
 767 |         )
 768 | 
 769 |     def get_display_name(self, user_id):
 770 |         content = self._send("GET", "/profile/%s/displayname" % user_id)
 771 |         return content.get('displayname', None)
 772 | 
 773 |     def set_display_name(self, user_id, display_name):
 774 |         content = {"displayname": display_name}
 775 |         return self._send("PUT", "/profile/%s/displayname" % user_id, content)
 776 | 
 777 |     def get_avatar_url(self, user_id):
 778 |         content = self._send("GET", "/profile/%s/avatar_url" % user_id)
 779 |         return content.get('avatar_url', None)
 780 | 
 781 |     def set_avatar_url(self, user_id, avatar_url):
 782 |         content = {"avatar_url": avatar_url}
 783 |         return self._send("PUT", "/profile/%s/avatar_url" % user_id, content)
 784 | 
 785 |     def get_download_url(self, mxcurl):
 786 |         if mxcurl.startswith('mxc://'):
 787 |             return self._base_url + "/_matrix/media/r0/download/" + mxcurl[6:]
 788 |         else:
 789 |             raise ValueError("MXC URL did not begin with 'mxc://'")
 790 | 
 791 |     def media_download(self, mxcurl, allow_remote=True):
 792 |         """Download raw media from provided mxc URL.
 793 | 
 794 |         Args:
 795 |             mxcurl (str): mxc media URL.
 796 |             allow_remote (bool): indicates to the server that it should not
 797 |                 attempt to fetch the media if it is deemed remote. Defaults
 798 |                 to true if not provided.
 799 |         """
 800 |         query_params = {}
 801 |         if not allow_remote:
 802 |             query_params["allow_remote"] = False
 803 |         if mxcurl.startswith('mxc://'):
 804 |             return self._send(
 805 |                 "GET", mxcurl[6:],
 806 |                 api_path="/_matrix/media/r0/download/",
 807 |                 query_params=query_params,
 808 |                 return_json=False
 809 |             )
 810 |         else:
 811 |             raise ValueError(
 812 |                 "MXC URL '%s' did not begin with 'mxc://'" % mxcurl
 813 |             )
 814 | 
 815 |     def get_thumbnail(self, mxcurl, width, height, method='scale', allow_remote=True):
 816 |         """Download raw media thumbnail from provided mxc URL.
 817 | 
 818 |         Args:
 819 |             mxcurl (str): mxc media URL
 820 |             width (int): desired thumbnail width
 821 |             height (int): desired thumbnail height
 822 |             method (str): thumb creation method. Must be
 823 |                 in ['scale', 'crop']. Default 'scale'.
 824 |             allow_remote (bool): indicates to the server that it should not
 825 |                 attempt to fetch the media if it is deemed remote. Defaults
 826 |                 to true if not provided.
 827 |         """
 828 |         if method not in ['scale', 'crop']:
 829 |             raise ValueError(
 830 |                 "Unsupported thumb method '%s'" % method
 831 |             )
 832 |         query_params = {
 833 |                     "width": width,
 834 |                     "height": height,
 835 |                     "method": method
 836 |                 }
 837 |         if not allow_remote:
 838 |             query_params["allow_remote"] = False
 839 |         if mxcurl.startswith('mxc://'):
 840 |             return self._send(
 841 |                 "GET", mxcurl[6:],
 842 |                 query_params=query_params,
 843 |                 api_path="/_matrix/media/r0/thumbnail/",
 844 |                 return_json=False
 845 |             )
 846 |         else:
 847 |             raise ValueError(
 848 |                 "MXC URL '%s' did not begin with 'mxc://'" % mxcurl
 849 |             )
 850 | 
 851 |     def get_url_preview(self, url, ts=None):
 852 |         """Get preview for URL.
 853 | 
 854 |         Args:
 855 |             url (str): URL to get a preview
 856 |             ts (double): The preferred point in time to return
 857 |                  a preview for. The server may return a newer
 858 |                  version if it does not have the requested
 859 |                  version available.
 860 |         """
 861 |         params = {'url': url}
 862 |         if ts:
 863 |             params['ts'] = ts
 864 |         return self._send(
 865 |             "GET", "",
 866 |             query_params=params,
 867 |             api_path="/_matrix/media/r0/preview_url"
 868 |         )
 869 | 
 870 |     def get_room_id(self, room_alias):
 871 |         """Get room id from its alias.
 872 | 
 873 |         Args:
 874 |             room_alias (str): The room alias name.
 875 | 
 876 |         Returns:
 877 |             Wanted room's id.
 878 |         """
 879 |         content = self._send("GET", "/directory/room/{}".format(quote(room_alias)))
 880 |         return content.get("room_id", None)
 881 | 
 882 |     def set_room_alias(self, room_id, room_alias):
 883 |         """Set alias to room id
 884 | 
 885 |         Args:
 886 |             room_id (str): The room id.
 887 |             room_alias (str): The room wanted alias name.
 888 |         """
 889 |         data = {
 890 |             "room_id": room_id
 891 |         }
 892 | 
 893 |         return self._send("PUT", "/directory/room/{}".format(quote(room_alias)),
 894 |                           content=data)
 895 | 
 896 |     def remove_room_alias(self, room_alias):
 897 |         """Remove mapping of an alias
 898 | 
 899 |         Args:
 900 |             room_alias(str): The alias to be removed.
 901 | 
 902 |         Raises:
 903 |             MatrixRequestError
 904 |         """
 905 |         return self._send("DELETE", "/directory/room/{}".format(quote(room_alias)))
 906 | 
 907 |     def get_room_members(self, room_id):
 908 |         """Get the list of members for this room.
 909 | 
 910 |         Args:
 911 |             room_id (str): The room to get the member events for.
 912 |         """
 913 |         return self._send("GET", "/rooms/{}/members".format(quote(room_id)))
 914 | 
 915 |     def set_join_rule(self, room_id, join_rule):
 916 |         """Set the rule for users wishing to join the room.
 917 | 
 918 |         Args:
 919 |             room_id(str): The room to set the rules for.
 920 |             join_rule(str): The chosen rule. One of: ["public", "knock",
 921 |                 "invite", "private"]
 922 |         """
 923 |         content = {
 924 |             "join_rule": join_rule
 925 |         }
 926 |         return self.send_state_event(room_id, "m.room.join_rules", content)
 927 | 
 928 |     def set_guest_access(self, room_id, guest_access):
 929 |         """Set the guest access policy of the room.
 930 | 
 931 |         Args:
 932 |             room_id(str): The room to set the rules for.
 933 |             guest_access(str): Wether guests can join. One of: ["can_join",
 934 |                 "forbidden"]
 935 |         """
 936 |         content = {
 937 |             "guest_access": guest_access
 938 |         }
 939 |         return self.send_state_event(room_id, "m.room.guest_access", content)
 940 | 
 941 |     def get_devices(self):
 942 |         """Gets information about all devices for the current user."""
 943 |         return self._send("GET", "/devices")
 944 | 
 945 |     def get_device(self, device_id):
 946 |         """Gets information on a single device, by device id."""
 947 |         return self._send("GET", "/devices/%s" % device_id)
 948 | 
 949 |     def update_device_info(self, device_id, display_name):
 950 |         """Update the display name of a device.
 951 | 
 952 |         Args:
 953 |             device_id (str): The device ID of the device to update.
 954 |             display_name (str): New display name for the device.
 955 |         """
 956 |         content = {
 957 |             "display_name": display_name
 958 |         }
 959 |         return self._send("PUT", "/devices/%s" % device_id, content=content)
 960 | 
 961 |     def delete_device(self, auth_body, device_id):
 962 |         """Deletes the given device, and invalidates any access token associated with it.
 963 | 
 964 |         NOTE: This endpoint uses the User-Interactive Authentication API.
 965 | 
 966 |         Args:
 967 |             auth_body (dict): Authentication params.
 968 |             device_id (str): The device ID of the device to delete.
 969 |         """
 970 |         content = {
 971 |             "auth": auth_body
 972 |         }
 973 |         return self._send("DELETE", "/devices/%s" % device_id, content=content)
 974 | 
 975 |     def delete_devices(self, auth_body, devices):
 976 |         """Bulk deletion of devices.
 977 | 
 978 |         NOTE: This endpoint uses the User-Interactive Authentication API.
 979 | 
 980 |         Args:
 981 |             auth_body (dict): Authentication params.
 982 |             devices (list): List of device ID"s to delete.
 983 |         """
 984 |         content = {
 985 |             "auth": auth_body,
 986 |             "devices": devices
 987 |         }
 988 |         return self._send("POST", "/delete_devices", content=content)
 989 | 
 990 |     def upload_keys(self, device_keys=None, one_time_keys=None):
 991 |         """Publishes end-to-end encryption keys for the device.
 992 | 
 993 |         Said device must be the one used when logging in.
 994 | 
 995 |         Args:
 996 |             device_keys (dict): Optional. Identity keys for the device. The required
 997 |                 keys are:
 998 | 
 999 |                 | user_id (str): The ID of the user the device belongs to. Must match
1000 |                     the user ID used when logging in.
1001 |                 | device_id (str): The ID of the device these keys belong to. Must match
1002 |                     the device ID used when logging in.
1003 |                 | algorithms (list<str>): The encryption algorithms supported by this
1004 |                     device.
1005 |                 | keys (dict): Public identity keys. Should be formatted as
1006 |                     <algorithm:device_id>: <key>.
1007 |                 | signatures (dict): Signatures for the device key object. Should be
1008 |                     formatted as <user_id>: {<algorithm:device_id>: <key>}
1009 | 
1010 |             one_time_keys (dict): Optional. One-time public keys. Should be
1011 |                 formatted as <algorithm:key_id>: <key>, the key format being
1012 |                 determined by the algorithm.
1013 |         """
1014 |         content = {}
1015 |         if device_keys:
1016 |             content["device_keys"] = device_keys
1017 |         if one_time_keys:
1018 |             content["one_time_keys"] = one_time_keys
1019 |         return self._send("POST", "/keys/upload", content=content)
1020 | 
1021 |     def query_keys(self, user_devices, timeout=None, token=None):
1022 |         """Query HS for public keys by user and optionally device.
1023 | 
1024 |         Args:
1025 |             user_devices (dict): The devices whose keys to download. Should be
1026 |                 formatted as <user_id>: [<device_ids>]. No device_ids indicates
1027 |                 all devices for the corresponding user.
1028 |             timeout (int): Optional. The time (in milliseconds) to wait when
1029 |                 downloading keys from remote servers.
1030 |             token (str): Optional. If the client is fetching keys as a result of
1031 |                 a device update received in a sync request, this should be the
1032 |                 'since' token of that sync request, or any later sync token.
1033 |         """
1034 |         content = {"device_keys": user_devices}
1035 |         if timeout:
1036 |             content["timeout"] = timeout
1037 |         if token:
1038 |             content["token"] = token
1039 |         return self._send("POST", "/keys/query", content=content)
1040 | 
1041 |     def claim_keys(self, key_request, timeout=None):
1042 |         """Claims one-time keys for use in pre-key messages.
1043 | 
1044 |         Args:
1045 |             key_request (dict): The keys to be claimed. Format should be
1046 |                 <user_id>: { <device_id>: <algorithm> }.
1047 |             timeout (int): Optional. The time (in milliseconds) to wait when
1048 |                 downloading keys from remote servers.
1049 |         """
1050 |         content = {"one_time_keys": key_request}
1051 |         if timeout:
1052 |             content["timeout"] = timeout
1053 |         return self._send("POST", "/keys/claim", content=content)
1054 | 
1055 |     def key_changes(self, from_token, to_token):
1056 |         """Gets a list of users who have updated their device identity keys.
1057 | 
1058 |         Args:
1059 |             from_token (str): The desired start point of the list. Should be the
1060 |                 next_batch field from a response to an earlier call to /sync.
1061 |             to_token (str): The desired end point of the list. Should be the next_batch
1062 |                 field from a recent call to /sync - typically the most recent such call.
1063 |         """
1064 |         params = {"from": from_token, "to": to_token}
1065 |         return self._send("GET", "/keys/changes", query_params=params)
1066 | 
1067 |     def send_to_device(self, event_type, messages, txn_id=None):
1068 |         """Sends send-to-device events to a set of client devices.
1069 | 
1070 |         Args:
1071 |             event_type (str): The type of event to send.
1072 |             messages (dict): The messages to send. Format should be
1073 |                 <user_id>: {<device_id>: <event_content>}.
1074 |                 The device ID may also be '*', meaning all known devices for the user.
1075 |             txn_id (str): Optional. The transaction ID for this event, will be generated
1076 |                 automatically otherwise.
1077 |         """
1078 |         txn_id = txn_id if txn_id else self._make_txn_id()
1079 |         return self._send(
1080 |             "PUT",
1081 |             "/sendToDevice/{}/{}".format(event_type, txn_id),
1082 |             content={"messages": messages}
1083 |         )
1084 | 
1085 |     def _make_txn_id(self):
1086 |         txn_id = str(self.txn_id) + str(int(time() * 1000))
1087 |         self.txn_id += 1
1088 |         return txn_id
1089 | 
1090 |     def whoami(self):
1091 |         """Determine user_id for authenticated user.
1092 |         """
1093 |         if not self.token:
1094 |             raise MatrixError("Authentication required.")
1095 |         return self._send(
1096 |             "GET",
1097 |             "/account/whoami"
1098 |         )
1099 | 


--------------------------------------------------------------------------------
/matrix_client/checks.py:
--------------------------------------------------------------------------------
 1 | # -*- coding: utf-8 -*-
 2 | # Copyright 2015 OpenMarket Ltd
 3 | #
 4 | # Licensed under the Apache License, Version 2.0 (the "License");
 5 | # you may not use this file except in compliance with the License.
 6 | # You may obtain a copy of the License at
 7 | #
 8 | #     http://www.apache.org/licenses/LICENSE-2.0
 9 | #
10 | # Unless required by applicable law or agreed to in writing, software
11 | # distributed under the License is distributed on an "AS IS" BASIS,
12 | # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
13 | # See the License for the specific language governing permissions and
14 | # limitations under the License.
15 | 
16 | 
17 | def check_room_id(room_id):
18 |     if not room_id.startswith("!"):
19 |         raise ValueError("RoomIDs start with !")
20 | 
21 |     if ":" not in room_id:
22 |         raise ValueError("RoomIDs must have a domain component, seperated by a :")
23 | 
24 | 
25 | def check_user_id(user_id):
26 |     if not user_id.startswith("@"):
27 |         raise ValueError("UserIDs start with @")
28 | 
29 |     if ":" not in user_id:
30 |         raise ValueError("UserIDs must have a domain component, seperated by a :")
31 | 


--------------------------------------------------------------------------------
/matrix_client/client.py:
--------------------------------------------------------------------------------
  1 | # -*- coding: utf-8 -*-
  2 | # Copyright 2015 OpenMarket Ltd
  3 | #
  4 | # Licensed under the Apache License, Version 2.0 (the "License");
  5 | # you may not use this file except in compliance with the License.
  6 | # You may obtain a copy of the License at
  7 | #
  8 | #     http://www.apache.org/licenses/LICENSE-2.0
  9 | #
 10 | # Unless required by applicable law or agreed to in writing, software
 11 | # distributed under the License is distributed on an "AS IS" BASIS,
 12 | # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 13 | # See the License for the specific language governing permissions and
 14 | # limitations under the License.
 15 | from .api import MatrixHttpApi
 16 | from .errors import MatrixRequestError, MatrixUnexpectedResponse
 17 | from .room import Room
 18 | from .user import User
 19 | try:
 20 |     from .crypto.olm_device import OlmDevice
 21 |     ENCRYPTION_SUPPORT = True
 22 | except ImportError:
 23 |     ENCRYPTION_SUPPORT = False
 24 | from threading import Thread
 25 | from time import sleep
 26 | from uuid import uuid4
 27 | from warnings import warn
 28 | import logging
 29 | import sys
 30 | 
 31 | logger = logging.getLogger(__name__)
 32 | 
 33 | 
 34 | # Cache constants used when instantiating Matrix Client to specify level of caching
 35 | class CACHE(int):
 36 |     pass
 37 | 
 38 | 
 39 | CACHE.NONE = CACHE(-1)
 40 | CACHE.SOME = CACHE(0)
 41 | CACHE.ALL = CACHE(1)
 42 | # TODO: rather than having CACHE.NONE as kwarg to MatrixClient, there should be a separate
 43 | # LightweightMatrixClient that only implements global listeners and doesn't hook into
 44 | # User, Room, etc. classes at all.
 45 | 
 46 | 
 47 | class MatrixClient(object):
 48 |     """
 49 |     The client API for Matrix. For the raw HTTP calls, see MatrixHttpApi.
 50 | 
 51 |     Args:
 52 |         base_url (str): The url of the HS preceding /_matrix.
 53 |             e.g. (ex: https://localhost:8008 )
 54 |         token (Optional[str]): If you have an access token
 55 |             supply it here.
 56 |         user_id (Optional[str]): Optional. Obsolete. For backward compatibility.
 57 |         valid_cert_check (bool): Check the homeservers
 58 |             certificate on connections?
 59 |         cache_level (CACHE): One of CACHE.NONE, CACHE.SOME, or
 60 |             CACHE.ALL (defined in module namespace).
 61 |         encryption (bool): Optional. Whether or not to enable end-to-end encryption
 62 |             support.
 63 |         encryption_conf (dict): Optional. Configuration parameters for encryption.
 64 |             Refer to :func:`~matrix_client.crypto.olm_device.OlmDevice` for supported
 65 |             options, since it will be passed to this class.
 66 | 
 67 |     Returns:
 68 |         `MatrixClient`
 69 | 
 70 |     Raises:
 71 |         `MatrixRequestError`, `ValueError`
 72 | 
 73 |     Examples:
 74 | 
 75 |         Create a new user and send a message::
 76 | 
 77 |             client = MatrixClient("https://matrix.org")
 78 |             token = client.register_with_password(username="foobar",
 79 |                 password="monkey")
 80 |             room = client.create_room("myroom")
 81 |             room.send_image(file_like_object)
 82 | 
 83 |         Send a message with an already logged in user::
 84 | 
 85 |             client = MatrixClient("https://matrix.org", token="foobar",
 86 |                 user_id="@foobar:matrix.org")
 87 |             client.add_listener(func)  # NB: event stream callback
 88 |             client.rooms[0].add_listener(func)  # NB: callbacks just for this room.
 89 |             room = client.join_room("#matrix:matrix.org")
 90 |             response = room.send_text("Hello!")
 91 |             response = room.kick("@bob:matrix.org")
 92 | 
 93 |         Incoming event callbacks (scopes)::
 94 | 
 95 |             def user_callback(user, incoming_event):
 96 |                 pass
 97 | 
 98 |             def room_callback(room, incoming_event):
 99 |                 pass
100 | 
101 |             def global_callback(incoming_event):
102 |                 pass
103 | 
104 |     Attributes:
105 |         users (dict): A map from user ID to :class:`.User` object.
106 |             It is populated automatically while tracking the membership in rooms, and
107 |             shouldn't be modified directly.
108 |             A :class:`.User` object in this dict is shared between all :class:`.Room`
109 |             objects where the corresponding user is joined.
110 |     """
111 | 
112 |     def __init__(self, base_url, token=None, user_id=None,
113 |                  valid_cert_check=True, sync_filter_limit=20,
114 |                  cache_level=CACHE.ALL, encryption=False, encryption_conf=None):
115 |         if user_id:
116 |             warn(
117 |                 "user_id is deprecated. "
118 |                 "Now it is requested from the server.", DeprecationWarning
119 |             )
120 | 
121 |         if encryption and not ENCRYPTION_SUPPORT:
122 |             raise ValueError("Failed to enable encryption. Please make sure the olm "
123 |                              "library is available.")
124 | 
125 |         self.api = MatrixHttpApi(base_url, token)
126 |         self.api.validate_certificate(valid_cert_check)
127 |         self.listeners = []
128 |         self.presence_listeners = {}
129 |         self.invite_listeners = []
130 |         self.left_listeners = []
131 |         self.ephemeral_listeners = []
132 |         self.device_id = None
133 |         self._encryption = encryption
134 |         self.encryption_conf = encryption_conf or {}
135 |         self.olm_device = None
136 |         if isinstance(cache_level, CACHE):
137 |             self._cache_level = cache_level
138 |         else:
139 |             self._cache_level = CACHE.ALL
140 |             raise ValueError(
141 |                 "cache_level must be one of CACHE.NONE, CACHE.SOME, CACHE.ALL"
142 |             )
143 | 
144 |         self.sync_token = None
145 |         self.sync_filter = '{ "room": { "timeline" : { "limit" : %i } } }' \
146 |             % sync_filter_limit
147 |         self.sync_thread = None
148 |         self.should_listen = False
149 | 
150 |         """ Time to wait before attempting a /sync request after failing."""
151 |         self.bad_sync_timeout_limit = 60 * 60
152 |         self.rooms = {
153 |             # room_id: Room
154 |         }
155 |         self.users = {
156 |             # user_id: User
157 |         }
158 |         if token:
159 |             response = self.api.whoami()
160 |             self.user_id = response["user_id"]
161 |             self._sync()
162 | 
163 |     def get_sync_token(self):
164 |         warn("get_sync_token is deprecated. Directly access MatrixClient.sync_token.",
165 |              DeprecationWarning)
166 |         return self.sync_token
167 | 
168 |     def set_sync_token(self, token):
169 |         warn("set_sync_token is deprecated. Directly access MatrixClient.sync_token.",
170 |              DeprecationWarning)
171 |         self.sync_token = token
172 | 
173 |     def set_user_id(self, user_id):
174 |         warn("set_user_id is deprecated. Directly access MatrixClient.user_id.",
175 |              DeprecationWarning)
176 |         self.user_id = user_id
177 | 
178 |     # TODO: combine register methods into single register method controlled by kwargs
179 |     def register_as_guest(self):
180 |         """ Register a guest account on this HS.
181 |         Note: HS must have guest registration enabled.
182 |         Returns:
183 |             str: Access Token
184 |         Raises:
185 |             MatrixRequestError
186 |         """
187 |         response = self.api.register(auth_body=None, kind='guest')
188 |         return self._post_registration(response)
189 | 
190 |     def register_with_password(self, username, password):
191 |         """ Register for a new account on this HS.
192 | 
193 |         Args:
194 |             username (str): Account username
195 |             password (str): Account password
196 | 
197 |         Returns:
198 |             str: Access Token
199 | 
200 |         Raises:
201 |             MatrixRequestError
202 |         """
203 |         response = self.api.register(
204 |                 auth_body={"type": "m.login.dummy"},
205 |                 kind='user',
206 |                 username=username,
207 |                 password=password,
208 |         )
209 |         return self._post_registration(response)
210 | 
211 |     def _post_registration(self, response):
212 |         self.user_id = response["user_id"]
213 |         self.token = response["access_token"]
214 |         self.hs = response["home_server"]
215 |         self.api.token = self.token
216 |         self._sync()
217 |         return self.token
218 | 
219 |     def login_with_password_no_sync(self, username, password):
220 |         """Deprecated. Use ``login`` with ``sync=False``.
221 | 
222 |         Login to the homeserver.
223 | 
224 |         Args:
225 |             username (str): Account username
226 |             password (str): Account password
227 | 
228 |         Returns:
229 |             str: Access token
230 | 
231 |         Raises:
232 |             MatrixRequestError
233 |         """
234 |         warn("login_with_password_no_sync is deprecated. Use login with sync=False.",
235 |              DeprecationWarning)
236 |         return self.login(username, password, sync=False)
237 | 
238 |     def login_with_password(self, username, password, limit=10):
239 |         """Deprecated. Use ``login`` with ``sync=True``.
240 | 
241 |         Login to the homeserver.
242 | 
243 |         Args:
244 |             username (str): Account username
245 |             password (str): Account password
246 |             limit (int): Deprecated. How many messages to return when syncing.
247 |                 This will be replaced by a filter API in a later release.
248 | 
249 |         Returns:
250 |             str: Access token
251 | 
252 |         Raises:
253 |             MatrixRequestError
254 |         """
255 |         warn("login_with_password is deprecated. Use login with sync=True.",
256 |              DeprecationWarning)
257 |         return self.login(username, password, limit, sync=True)
258 | 
259 |     def login(self, username, password, limit=10, sync=True, device_id=None):
260 |         """Login to the homeserver.
261 | 
262 |         Args:
263 |             username (str): Account username
264 |             password (str): Account password
265 |             limit (int): Deprecated. How many messages to return when syncing.
266 |                 This will be replaced by a filter API in a later release.
267 |             sync (bool): Optional. Whether to initiate a /sync request after logging in.
268 |             device_id (str): Optional. ID of the client device. The server will
269 |                 auto-generate a device_id if this is not specified.
270 | 
271 |         Returns:
272 |             str: Access token
273 | 
274 |         Raises:
275 |             MatrixRequestError
276 |         """
277 |         response = self.api.login(
278 |             "m.login.password", user=username, password=password, device_id=device_id
279 |         )
280 |         self.user_id = response["user_id"]
281 |         self.token = response["access_token"]
282 |         self.hs = response["home_server"]
283 |         self.api.token = self.token
284 |         self.device_id = response["device_id"]
285 | 
286 |         if self._encryption:
287 |             self.olm_device = OlmDevice(
288 |                 self.api, self.user_id, self.device_id, **self.encryption_conf)
289 |             self.olm_device.upload_identity_keys()
290 |             self.olm_device.upload_one_time_keys()
291 | 
292 |         if sync:
293 |             """ Limit Filter """
294 |             self.sync_filter = '{ "room": { "timeline" : { "limit" : %i } } }' % limit
295 |             self._sync()
296 |         return self.token
297 | 
298 |     def logout(self):
299 |         """ Logout from the homeserver.
300 |         """
301 |         self.stop_listener_thread()
302 |         self.api.logout()
303 | 
304 |     # TODO: move room creation/joining to User class for future application service usage
305 |     # NOTE: we may want to leave thin wrappers here for convenience
306 |     def create_room(self, alias=None, is_public=False, invitees=None):
307 |         """ Create a new room on the homeserver.
308 | 
309 |         Args:
310 |             alias (str): The canonical_alias of the room.
311 |             is_public (bool):  The public/private visibility of the room.
312 |             invitees (str[]): A set of user ids to invite into the room.
313 | 
314 |         Returns:
315 |             Room
316 | 
317 |         Raises:
318 |             MatrixRequestError
319 |         """
320 |         response = self.api.create_room(alias=alias,
321 |                                         is_public=is_public,
322 |                                         invitees=invitees)
323 |         return self._mkroom(response["room_id"])
324 | 
325 |     def join_room(self, room_id_or_alias):
326 |         """ Join a room.
327 | 
328 |         Args:
329 |             room_id_or_alias (str): Room ID or an alias.
330 | 
331 |         Returns:
332 |             Room
333 | 
334 |         Raises:
335 |             MatrixRequestError
336 |         """
337 |         response = self.api.join_room(room_id_or_alias)
338 |         room_id = (
339 |             response["room_id"] if "room_id" in response else room_id_or_alias
340 |         )
341 |         return self._mkroom(room_id)
342 | 
343 |     def get_rooms(self):
344 |         """ Deprecated. Return a dict of {room_id: Room objects} that the user has joined.
345 | 
346 |         Returns:
347 |             Room{}: Rooms the user has joined.
348 |         """
349 |         warn("get_rooms is deprecated. Directly access MatrixClient.rooms.",
350 |              DeprecationWarning)
351 |         return self.rooms
352 | 
353 |     # TODO: create Listener class and push as much of this logic there as possible
354 |     # NOTE: listeners related to things in rooms should be attached to Room objects
355 |     def add_listener(self, callback, event_type=None):
356 |         """ Add a listener that will send a callback when the client recieves
357 |         an event.
358 | 
359 |         Args:
360 |             callback (func(roomchunk)): Callback called when an event arrives.
361 |             event_type (str): The event_type to filter for.
362 | 
363 |         Returns:
364 |             uuid.UUID: Unique id of the listener, can be used to identify the listener.
365 |         """
366 |         listener_uid = uuid4()
367 |         # TODO: listeners should be stored in dict and accessed/deleted directly. Add
368 |         # convenience method such that MatrixClient.listeners.new(Listener(...)) performs
369 |         # MatrixClient.listeners[uuid4()] = Listener(...)
370 |         self.listeners.append(
371 |             {
372 |                 'uid': listener_uid,
373 |                 'callback': callback,
374 |                 'event_type': event_type
375 |             }
376 |         )
377 |         return listener_uid
378 | 
379 |     def remove_listener(self, uid):
380 |         """ Remove listener with given uid.
381 | 
382 |         Args:
383 |             uuid.UUID: Unique id of the listener to remove.
384 |         """
385 |         self.listeners[:] = (listener for listener in self.listeners
386 |                              if listener['uid'] != uid)
387 | 
388 |     def add_presence_listener(self, callback):
389 |         """ Add a presence listener that will send a callback when the client receives
390 |         a presence update.
391 | 
392 |         Args:
393 |             callback (func(roomchunk)): Callback called when a presence update arrives.
394 | 
395 |         Returns:
396 |             uuid.UUID: Unique id of the listener, can be used to identify the listener.
397 |         """
398 |         listener_uid = uuid4()
399 |         self.presence_listeners[listener_uid] = callback
400 |         return listener_uid
401 | 
402 |     def remove_presence_listener(self, uid):
403 |         """ Remove presence listener with given uid
404 | 
405 |         Args:
406 |             uuid.UUID: Unique id of the listener to remove
407 |         """
408 |         self.presence_listeners.pop(uid)
409 | 
410 |     def add_ephemeral_listener(self, callback, event_type=None):
411 |         """ Add an ephemeral listener that will send a callback when the client recieves
412 |         an ephemeral event.
413 | 
414 |         Args:
415 |             callback (func(roomchunk)): Callback called when an ephemeral event arrives.
416 |             event_type (str): The event_type to filter for.
417 | 
418 |         Returns:
419 |             uuid.UUID: Unique id of the listener, can be used to identify the listener.
420 |         """
421 |         listener_id = uuid4()
422 |         self.ephemeral_listeners.append(
423 |             {
424 |                 'uid': listener_id,
425 |                 'callback': callback,
426 |                 'event_type': event_type
427 |             }
428 |         )
429 |         return listener_id
430 | 
431 |     def remove_ephemeral_listener(self, uid):
432 |         """ Remove ephemeral listener with given uid.
433 | 
434 |         Args:
435 |             uuid.UUID: Unique id of the listener to remove.
436 |         """
437 |         self.ephemeral_listeners[:] = (listener for listener in self.ephemeral_listeners
438 |                                        if listener['uid'] != uid)
439 | 
440 |     def add_invite_listener(self, callback):
441 |         """ Add a listener that will send a callback when the client receives
442 |         an invite.
443 | 
444 |         Args:
445 |             callback (func(room_id, state)): Callback called when an invite arrives.
446 |         """
447 |         self.invite_listeners.append(callback)
448 | 
449 |     def add_leave_listener(self, callback):
450 |         """ Add a listener that will send a callback when the client has left a room.
451 | 
452 |         Args:
453 |             callback (func(room_id, room)): Callback called when the client
454 |             has left a room.
455 |         """
456 |         self.left_listeners.append(callback)
457 | 
458 |     def listen_for_events(self, timeout_ms=30000):
459 |         """
460 |         This function just calls _sync()
461 | 
462 |         In a future version of this sdk, this function will be deprecated and
463 |         _sync method will be renamed sync with the intention of it being called
464 |         by downstream code.
465 | 
466 |         Args:
467 |             timeout_ms (int): How long to poll the Home Server for before
468 |                retrying.
469 |         """
470 |         # TODO: see docstring
471 |         self._sync(timeout_ms)
472 | 
473 |     def listen_forever(self, timeout_ms=30000, exception_handler=None,
474 |                        bad_sync_timeout=5):
475 |         """ Keep listening for events forever.
476 | 
477 |         Args:
478 |             timeout_ms (int): How long to poll the Home Server for before
479 |                retrying.
480 |             exception_handler (func(exception)): Optional exception handler
481 |                function which can be used to handle exceptions in the caller
482 |                thread.
483 |             bad_sync_timeout (int): Base time to wait after an error before
484 |                 retrying. Will be increased according to exponential backoff.
485 |         """
486 |         _bad_sync_timeout = bad_sync_timeout
487 |         self.should_listen = True
488 |         while (self.should_listen):
489 |             try:
490 |                 self._sync(timeout_ms)
491 |                 _bad_sync_timeout = bad_sync_timeout
492 |             # TODO: we should also handle MatrixHttpLibError for retry in case no response
493 |             except MatrixRequestError as e:
494 |                 logger.warning("A MatrixRequestError occured during sync.")
495 |                 if e.code >= 500:
496 |                     logger.warning("Problem occured serverside. Waiting %i seconds",
497 |                                    bad_sync_timeout)
498 |                     sleep(bad_sync_timeout)
499 |                     _bad_sync_timeout = min(_bad_sync_timeout * 2,
500 |                                             self.bad_sync_timeout_limit)
501 |                 elif exception_handler is not None:
502 |                     exception_handler(e)
503 |                 else:
504 |                     raise
505 |             except Exception as e:
506 |                 logger.exception("Exception thrown during sync")
507 |                 if exception_handler is not None:
508 |                     exception_handler(e)
509 |                 else:
510 |                     raise
511 | 
512 |     def start_listener_thread(self, timeout_ms=30000, exception_handler=None):
513 |         """ Start a listener thread to listen for events in the background.
514 | 
515 |         Args:
516 |             timeout (int): How long to poll the Home Server for before
517 |                retrying.
518 |             exception_handler (func(exception)): Optional exception handler
519 |                function which can be used to handle exceptions in the caller
520 |                thread.
521 |         """
522 |         try:
523 |             thread = Thread(target=self.listen_forever,
524 |                             args=(timeout_ms, exception_handler))
525 |             thread.daemon = True
526 |             self.sync_thread = thread
527 |             self.should_listen = True
528 |             thread.start()
529 |         except RuntimeError:
530 |             e = sys.exc_info()[0]
531 |             logger.error("Error: unable to start thread. %s", str(e))
532 | 
533 |     def stop_listener_thread(self):
534 |         """ Stop listener thread running in the background
535 |         """
536 |         if self.sync_thread:
537 |             self.should_listen = False
538 |             self.sync_thread.join()
539 |             self.sync_thread = None
540 | 
541 |     # TODO: move to User class. Consider creating lightweight Media class.
542 |     def upload(self, content, content_type, filename=None):
543 |         """ Upload content to the home server and recieve a MXC url.
544 | 
545 |         Args:
546 |             content (bytes): The data of the content.
547 |             content_type (str): The mimetype of the content.
548 |             filename (str): Optional. Filename of the content.
549 | 
550 |         Raises:
551 |             MatrixUnexpectedResponse: If the homeserver gave a strange response
552 |             MatrixRequestError: If the upload failed for some reason.
553 |         """
554 |         try:
555 |             response = self.api.media_upload(content, content_type, filename)
556 |             if "content_uri" in response:
557 |                 return response["content_uri"]
558 |             else:
559 |                 raise MatrixUnexpectedResponse(
560 |                     "The upload was successful, but content_uri wasn't found."
561 |                 )
562 |         except MatrixRequestError as e:
563 |             raise MatrixRequestError(
564 |                 code=e.code,
565 |                 content="Upload failed: %s" % e
566 |             )
567 | 
568 |     def _mkroom(self, room_id):
569 |         room = Room(self, room_id)
570 |         if self._encryption:
571 |             try:
572 |                 event = self.api.get_state_event(room_id, "m.room.encryption")
573 |                 if event["algorithm"] == "m.megolm.v1.aes-sha2":
574 |                     room.encrypted = True
575 |             except MatrixRequestError as e:
576 |                 if e.code != 404:
577 |                     raise
578 |         self.rooms[room_id] = room
579 |         return self.rooms[room_id]
580 | 
581 |     # TODO better handling of the blocking I/O caused by update_one_time_key_counts
582 |     def _sync(self, timeout_ms=30000):
583 |         response = self.api.sync(self.sync_token, timeout_ms, filter=self.sync_filter)
584 |         self.sync_token = response["next_batch"]
585 | 
586 |         if 'presence' in response and 'events' in response['presence']:
587 |             for presence_update in response['presence']['events']:
588 |                 for callback in self.presence_listeners.values():
589 |                     callback(presence_update)
590 | 
591 |         if self._encryption and 'device_one_time_keys_count' in response:
592 |             self.olm_device.update_one_time_key_counts(
593 |                 response['device_one_time_keys_count'])
594 | 
595 |         rooms = response.get("rooms", {})
596 |         if 'invite' in rooms:
597 |             for room_id, invite_room in rooms['invite'].items():
598 |                 for listener in self.invite_listeners:
599 |                     listener(room_id, invite_room['invite_state'])
600 | 
601 |         if 'leave' in rooms:
602 |             for room_id, left_room in rooms['leave'].items():
603 |                 for listener in self.left_listeners:
604 |                     listener(room_id, left_room)
605 |                 if room_id in self.rooms:
606 |                     del self.rooms[room_id]
607 | 
608 |         if 'join' in rooms:
609 |             for room_id, sync_room in rooms['join'].items():
610 |                 if room_id not in self.rooms:
611 |                     self._mkroom(room_id)
612 |                 room = self.rooms[room_id]
613 |                 # TODO: the rest of this for loop should be in room object method
614 |                 room.prev_batch = sync_room["timeline"]["prev_batch"]
615 | 
616 |                 if "state" in sync_room and "events" in sync_room["state"]:
617 |                     for event in sync_room["state"]["events"]:
618 |                         event['room_id'] = room_id
619 |                         room._process_state_event(event)
620 | 
621 |                 if "timeline" in sync_room and "events" in sync_room["timeline"]:
622 |                     for event in sync_room["timeline"]["events"]:
623 |                         event['room_id'] = room_id
624 |                         room._put_event(event)
625 | 
626 |                         # TODO: global listeners can still exist but work by each
627 |                         # room.listeners[uuid] having reference to global listener
628 | 
629 |                         # Dispatch for client (global) listeners
630 |                         for listener in self.listeners:
631 |                             if (
632 |                                 listener['event_type'] is None or
633 |                                 listener['event_type'] == event['type']
634 |                             ):
635 |                                 listener['callback'](event)
636 | 
637 |                 if "ephemeral" in sync_room and "events" in sync_room["ephemeral"]:
638 |                     for event in sync_room['ephemeral']['events']:
639 |                         event['room_id'] = room_id
640 |                         room._put_ephemeral_event(event)
641 | 
642 |                         for listener in self.ephemeral_listeners:
643 |                             if (
644 |                                 listener['event_type'] is None or
645 |                                 listener['event_type'] == event['type']
646 |                             ):
647 |                                 listener['callback'](event)
648 | 
649 |     def get_user(self, user_id):
650 |         """Deprecated. Return a User by their id.
651 | 
652 |         This method only instantiate a User, which should be done directly.
653 |         You can also use :attr:`users` in order to access a User object which
654 |         was created automatically.
655 | 
656 |         Args:
657 |             user_id (str): The matrix user id of a user.
658 |         """
659 |         warn("get_user is deprecated. Directly instantiate a User instead.",
660 |              DeprecationWarning)
661 |         return User(self.api, user_id)
662 | 
663 |     # TODO: move to Room class
664 |     def remove_room_alias(self, room_alias):
665 |         """Remove mapping of an alias
666 | 
667 |         Args:
668 |             room_alias(str): The alias to be removed.
669 | 
670 |         Returns:
671 |             bool: True if the alias is removed, False otherwise.
672 |         """
673 |         try:
674 |             self.api.remove_room_alias(room_alias)
675 |             return True
676 |         except MatrixRequestError:
677 |             return False
678 | 


--------------------------------------------------------------------------------
/matrix_client/crypto/__init__.py:
--------------------------------------------------------------------------------
https://raw.githubusercontent.com/matrix-org/matrix-python-sdk/887f5d55e16518a0a2bef4f2d6bff6ecf48d18c1/matrix_client/crypto/__init__.py


--------------------------------------------------------------------------------
/matrix_client/crypto/olm_device.py:
--------------------------------------------------------------------------------
  1 | import logging
  2 | 
  3 | import olm
  4 | from canonicaljson import encode_canonical_json
  5 | 
  6 | from matrix_client.checks import check_user_id
  7 | from matrix_client.crypto.one_time_keys import OneTimeKeysManager
  8 | 
  9 | logger = logging.getLogger(__name__)
 10 | 
 11 | 
 12 | class OlmDevice(object):
 13 |     """Manages the Olm cryptographic functions.
 14 | 
 15 |     Has a unique Olm account which holds identity keys.
 16 | 
 17 |     Args:
 18 |         api (MatrixHttpApi): The api object used to make requests.
 19 |         user_id (str): Matrix user ID. Must match the one used when logging in.
 20 |         device_id (str): Must match the one used when logging in.
 21 |         signed_keys_proportion (float): Optional. The proportion of signed one-time keys
 22 |             we should maintain on the HS compared to unsigned keys. The maximum value of
 23 |             ``1`` means only signed keys will be uploaded, while the minimum value of
 24 |             ``0`` means only unsigned keys. The actual amount of keys is determined at
 25 |             runtime from the given proportion and the maximum number of one-time keys
 26 |             we can physically hold.
 27 |         keys_threshold (float): Optional. Threshold below which a one-time key
 28 |             replenishment is triggered. Must be between ``0`` and ``1``. For example,
 29 |             ``0.1`` means that new one-time keys will be uploaded when there is less than
 30 |             10% of the maximum number of one-time keys on the server.
 31 |     """
 32 | 
 33 |     _olm_algorithm = 'm.olm.v1.curve25519-aes-sha2'
 34 |     _megolm_algorithm = 'm.megolm.v1.aes-sha2'
 35 |     _algorithms = [_olm_algorithm, _megolm_algorithm]
 36 | 
 37 |     def __init__(self,
 38 |                  api,
 39 |                  user_id,
 40 |                  device_id,
 41 |                  signed_keys_proportion=1,
 42 |                  keys_threshold=0.1):
 43 |         if not 0 <= signed_keys_proportion <= 1:
 44 |             raise ValueError('signed_keys_proportion must be between 0 and 1.')
 45 |         if not 0 <= keys_threshold <= 1:
 46 |             raise ValueError('keys_threshold must be between 0 and 1.')
 47 |         self.api = api
 48 |         check_user_id(user_id)
 49 |         self.user_id = user_id
 50 |         self.device_id = device_id
 51 |         self.olm_account = olm.Account()
 52 |         logger.info('Initialised Olm Device.')
 53 |         self.identity_keys = self.olm_account.identity_keys
 54 |         # Try to maintain half the number of one-time keys libolm can hold uploaded
 55 |         # on the HS. This is because some keys will be claimed by peers but not
 56 |         # used instantly, and we want them to stay in libolm, until the limit is reached
 57 |         # and it starts discarding keys, starting by the oldest.
 58 |         target_keys_number = self.olm_account.max_one_time_keys // 2
 59 |         self.one_time_keys_manager = OneTimeKeysManager(target_keys_number,
 60 |                                                         signed_keys_proportion,
 61 |                                                         keys_threshold)
 62 | 
 63 |     def upload_identity_keys(self):
 64 |         """Uploads this device's identity keys to HS.
 65 | 
 66 |         This device must be the one used when logging in.
 67 |         """
 68 |         device_keys = {
 69 |             'user_id': self.user_id,
 70 |             'device_id': self.device_id,
 71 |             'algorithms': self._algorithms,
 72 |             'keys': {'{}:{}'.format(alg, self.device_id): key
 73 |                      for alg, key in self.identity_keys.items()}
 74 |         }
 75 |         self.sign_json(device_keys)
 76 |         ret = self.api.upload_keys(device_keys=device_keys)
 77 |         self.one_time_keys_manager.server_counts = ret['one_time_key_counts']
 78 |         logger.info('Uploaded identity keys.')
 79 | 
 80 |     def upload_one_time_keys(self, force_update=False):
 81 |         """Uploads new one-time keys to the HS, if needed.
 82 | 
 83 |         Args:
 84 |             force_update (bool): Fetch the number of one-time keys currently on the HS
 85 |                 before uploading, even if we already know one. In most cases this should
 86 |                 not be necessary, as we get this value from sync responses.
 87 | 
 88 |         Returns:
 89 |             A dict containg the number of new keys that were uploaded for each key type
 90 |                 (signed_curve25519 or curve25519). The format is
 91 |                 ``<key_type>: <uploaded_number>``. If no keys of a given type have been
 92 |                 uploaded, the corresponding key will not be present. Consequently, an
 93 |                 empty dict indicates that no keys were uploaded.
 94 |         """
 95 |         if force_update or not self.one_time_keys_manager.server_counts:
 96 |             counts = self.api.upload_keys()['one_time_key_counts']
 97 |             self.one_time_keys_manager.server_counts = counts
 98 | 
 99 |         signed_keys_to_upload = self.one_time_keys_manager.signed_curve25519_to_upload
100 |         unsigned_keys_to_upload = self.one_time_keys_manager.curve25519_to_upload
101 | 
102 |         self.olm_account.generate_one_time_keys(signed_keys_to_upload +
103 |                                                 unsigned_keys_to_upload)
104 | 
105 |         one_time_keys = {}
106 |         keys = self.olm_account.one_time_keys['curve25519']
107 |         for i, key_id in enumerate(keys):
108 |             if i < signed_keys_to_upload:
109 |                 key = self.sign_json({'key': keys[key_id]})
110 |                 key_type = 'signed_curve25519'
111 |             else:
112 |                 key = keys[key_id]
113 |                 key_type = 'curve25519'
114 |             one_time_keys['{}:{}'.format(key_type, key_id)] = key
115 | 
116 |         ret = self.api.upload_keys(one_time_keys=one_time_keys)
117 |         self.one_time_keys_manager.server_counts = ret['one_time_key_counts']
118 |         self.olm_account.mark_keys_as_published()
119 | 
120 |         keys_uploaded = {}
121 |         if unsigned_keys_to_upload:
122 |             keys_uploaded['curve25519'] = unsigned_keys_to_upload
123 |         if signed_keys_to_upload:
124 |             keys_uploaded['signed_curve25519'] = signed_keys_to_upload
125 |         logger.info('Uploaded new one-time keys: %s.', keys_uploaded)
126 |         return keys_uploaded
127 | 
128 |     def update_one_time_key_counts(self, counts):
129 |         """Update data on one-time keys count and upload new ones if necessary.
130 | 
131 |         Args:
132 |             counts (dict): Counts of keys currently on the HS for each key type.
133 |         """
134 |         self.one_time_keys_manager.server_counts = counts
135 |         if self.one_time_keys_manager.should_upload():
136 |             logger.info('Uploading new one-time keys.')
137 |             self.upload_one_time_keys()
138 | 
139 |     def sign_json(self, json):
140 |         """Signs a JSON object.
141 | 
142 |         NOTE: The object is modified in-place and the return value can be ignored.
143 | 
144 |         As specified, this is done by encoding the JSON object without ``signatures`` or
145 |         keys grouped as ``unsigned``, using canonical encoding.
146 | 
147 |         Args:
148 |             json (dict): The JSON object to sign.
149 | 
150 |         Returns:
151 |             The same JSON object, with a ``signatures`` key added. It is formatted as
152 |             ``"signatures": ed25519:<device_id>: <base64_signature>``.
153 |         """
154 |         signatures = json.pop('signatures', {})
155 |         unsigned = json.pop('unsigned', None)
156 | 
157 |         signature_base64 = self.olm_account.sign(encode_canonical_json(json))
158 | 
159 |         key_id = 'ed25519:{}'.format(self.device_id)
160 |         signatures.setdefault(self.user_id, {})[key_id] = signature_base64
161 | 
162 |         json['signatures'] = signatures
163 |         if unsigned:
164 |             json['unsigned'] = unsigned
165 | 
166 |         return json
167 | 
168 |     def verify_json(self, json, user_key, user_id, device_id):
169 |         """Verifies a signed key object's signature.
170 | 
171 |         The object must have a 'signatures' key associated with an object of the form
172 |         `user_id: {key_id: signature}`.
173 | 
174 |         Args:
175 |             json (dict): The JSON object to verify.
176 |             user_key (str): The public ed25519 key which was used to sign the object.
177 |             user_id (str): The user who owns the device.
178 |             device_id (str): The device who owns the key.
179 | 
180 |         Returns:
181 |             True if the verification was successful, False if not.
182 |         """
183 |         try:
184 |             signatures = json.pop('signatures')
185 |         except KeyError:
186 |             return False
187 | 
188 |         key_id = 'ed25519:{}'.format(device_id)
189 |         try:
190 |             signature_base64 = signatures[user_id][key_id]
191 |         except KeyError:
192 |             json['signatures'] = signatures
193 |             return False
194 | 
195 |         unsigned = json.pop('unsigned', None)
196 | 
197 |         try:
198 |             olm.ed25519_verify(user_key, encode_canonical_json(json), signature_base64)
199 |             success = True
200 |         except olm.utility.OlmVerifyError:
201 |             success = False
202 | 
203 |         json['signatures'] = signatures
204 |         if unsigned:
205 |             json['unsigned'] = unsigned
206 | 
207 |         return success
208 | 


--------------------------------------------------------------------------------
/matrix_client/crypto/one_time_keys.py:
--------------------------------------------------------------------------------
 1 | class OneTimeKeysManager(object):
 2 |     """Handles one-time keys accounting for an OlmDevice."""
 3 | 
 4 |     def __init__(self, target_keys_number, signed_keys_proportion, keys_threshold):
 5 |         self.target_counts = {
 6 |             'signed_curve25519': int(round(signed_keys_proportion * target_keys_number)),
 7 |             'curve25519': int(round((1 - signed_keys_proportion) * target_keys_number)),
 8 |         }
 9 |         self._server_counts = {}
10 |         self.to_upload = {}
11 |         self.keys_threshold = keys_threshold
12 | 
13 |     @property
14 |     def server_counts(self):
15 |         return self._server_counts
16 | 
17 |     @server_counts.setter
18 |     def server_counts(self, server_counts):
19 |         self._server_counts = server_counts
20 |         self.update_keys_to_upload()
21 | 
22 |     def update_keys_to_upload(self):
23 |         for key_type, target_number in self.target_counts.items():
24 |             num_keys = self._server_counts.get(key_type, 0)
25 |             num_to_create = max(target_number - num_keys, 0)
26 |             self.to_upload[key_type] = num_to_create
27 | 
28 |     def should_upload(self):
29 |         if not self._server_counts:
30 |             return True
31 |         for key_type, target_number in self.target_counts.items():
32 |             if self._server_counts.get(key_type, 0) < target_number * self.keys_threshold:
33 |                 return True
34 |         return False
35 | 
36 |     @property
37 |     def curve25519_to_upload(self):
38 |         return self.to_upload.get('curve25519', 0)
39 | 
40 |     @property
41 |     def signed_curve25519_to_upload(self):
42 |         return self.to_upload.get('signed_curve25519', 0)
43 | 


--------------------------------------------------------------------------------
/matrix_client/errors.py:
--------------------------------------------------------------------------------
 1 | # -*- coding: utf-8 -*-
 2 | # Copyright 2015 OpenMarket Ltd
 3 | #
 4 | # Licensed under the Apache License, Version 2.0 (the "License");
 5 | # you may not use this file except in compliance with the License.
 6 | # You may obtain a copy of the License at
 7 | #
 8 | #     http://www.apache.org/licenses/LICENSE-2.0
 9 | #
10 | # Unless required by applicable law or agreed to in writing, software
11 | # distributed under the License is distributed on an "AS IS" BASIS,
12 | # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
13 | # See the License for the specific language governing permissions and
14 | # limitations under the License.
15 | 
16 | 
17 | class MatrixError(Exception):
18 |     """A generic Matrix error. Specific errors will subclass this."""
19 |     pass
20 | 
21 | 
22 | class MatrixUnexpectedResponse(MatrixError):
23 |     """The home server gave an unexpected response. """
24 | 
25 |     def __init__(self, content=""):
26 |         super(MatrixUnexpectedResponse, self).__init__(content)
27 |         self.content = content
28 | 
29 | 
30 | class MatrixRequestError(MatrixError):
31 |     """ The home server returned an error response. """
32 | 
33 |     def __init__(self, code=0, content=""):
34 |         super(MatrixRequestError, self).__init__("%d: %s" % (code, content))
35 |         self.code = code
36 |         self.content = content
37 | 
38 | 
39 | class MatrixHttpLibError(MatrixError):
40 |     """The library used for http requests raised an exception."""
41 | 
42 |     def __init__(self, original_exception, method, endpoint):
43 |         super(MatrixHttpLibError, self).__init__(
44 |             "Something went wrong in {} requesting {}: {}".format(method,
45 |                                                                   endpoint,
46 |                                                                   original_exception)
47 |         )
48 |         self.original_exception = original_exception
49 | 


--------------------------------------------------------------------------------
/matrix_client/room.py:
--------------------------------------------------------------------------------
  1 | # -*- coding: utf-8 -*-
  2 | # Copyright 2015 OpenMarket Ltd
  3 | # Copyright 2018 Adam Beckmeyer
  4 | #
  5 | # Licensed under the Apache License, Version 2.0 (the "License");
  6 | # you may not use this file except in compliance with the License.
  7 | # You may obtain a copy of the License at
  8 | #
  9 | #     http://www.apache.org/licenses/LICENSE-2.0
 10 | #
 11 | # Unless required by applicable law or agreed to in writing, software
 12 | # distributed under the License is distributed on an "AS IS" BASIS,
 13 | # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 14 | # See the License for the specific language governing permissions and
 15 | # limitations under the License.
 16 | import logging
 17 | import re
 18 | from uuid import uuid4
 19 | 
 20 | from .checks import check_room_id
 21 | from .user import User
 22 | from .errors import MatrixRequestError
 23 | 
 24 | logger = logging.getLogger(__name__)
 25 | 
 26 | 
 27 | class Room(object):
 28 |     """Call room-specific functions after joining a room from the client.
 29 | 
 30 |     NOTE: This should ideally be called from within the Client.
 31 |     NOTE: This does not verify the room with the Home Server.
 32 |     """
 33 | 
 34 |     def __init__(self, client, room_id):
 35 |         check_room_id(room_id)
 36 | 
 37 |         self.room_id = room_id
 38 |         self.client = client
 39 |         self.listeners = []
 40 |         self.state_listeners = []
 41 |         self.ephemeral_listeners = []
 42 |         self.events = []
 43 |         self.event_history_limit = 20
 44 |         self.name = None
 45 |         self.canonical_alias = None
 46 |         self.aliases = []
 47 |         self.topic = None
 48 |         self.invite_only = None
 49 |         self.guest_access = None
 50 |         self._prev_batch = None
 51 |         self._members = {}
 52 |         self.members_displaynames = {
 53 |             # user_id: displayname
 54 |         }
 55 |         self.encrypted = False
 56 | 
 57 |     def set_user_profile(self,
 58 |                          displayname=None,
 59 |                          avatar_url=None,
 60 |                          reason="Changing room profile information"):
 61 |         """Set user profile within a room.
 62 | 
 63 |         This sets displayname and avatar_url for the logged in user only in a
 64 |         specific room. It does not change the user's global user profile.
 65 |         """
 66 |         member = self.client.api.get_membership(self.room_id, self.client.user_id)
 67 |         if member["membership"] != "join":
 68 |             raise Exception("Can't set profile if you have not joined the room.")
 69 |         if displayname is None:
 70 |             displayname = member["displayname"]
 71 |         if avatar_url is None:
 72 |             avatar_url = member["avatar_url"]
 73 |         self.client.api.set_membership(
 74 |             self.room_id,
 75 |             self.client.user_id,
 76 |             'join',
 77 |             reason, {
 78 |                 "displayname": displayname,
 79 |                 "avatar_url": avatar_url
 80 |             }
 81 |         )
 82 | 
 83 |     @property
 84 |     def display_name(self):
 85 |         """Calculates the display name for a room."""
 86 |         if self.name:
 87 |             return self.name
 88 |         elif self.canonical_alias:
 89 |             return self.canonical_alias
 90 | 
 91 |         # Member display names without me
 92 |         members = [u.get_display_name(self) for u in self.get_joined_members() if
 93 |                    self.client.user_id != u.user_id]
 94 |         members.sort()
 95 | 
 96 |         if len(members) == 1:
 97 |             return members[0]
 98 |         elif len(members) == 2:
 99 |             return "{0} and {1}".format(members[0], members[1])
100 |         elif len(members) > 2:
101 |             return "{0} and {1} others".format(members[0], len(members) - 1)
102 |         else:  # len(members) <= 0 or not an integer
103 |             # TODO i18n
104 |             return "Empty room"
105 | 
106 |     def send_text(self, text):
107 |         """Send a plain text message to the room."""
108 |         return self.client.api.send_message(self.room_id, text)
109 | 
110 |     def get_html_content(self, html, body=None, msgtype="m.text"):
111 |         return {
112 |             "body": body if body else re.sub('<[^<]+?>', '', html),
113 |             "msgtype": msgtype,
114 |             "format": "org.matrix.custom.html",
115 |             "formatted_body": html
116 |         }
117 | 
118 |     def send_html(self, html, body=None, msgtype="m.text"):
119 |         """Send an html formatted message.
120 | 
121 |         Args:
122 |             html (str): The html formatted message to be sent.
123 |             body (str): The unformatted body of the message to be sent.
124 |         """
125 |         return self.client.api.send_message_event(
126 |             self.room_id, "m.room.message", self.get_html_content(html, body, msgtype))
127 | 
128 |     def set_account_data(self, type, account_data):
129 |         return self.client.api.set_room_account_data(
130 |             self.client.user_id, self.room_id, type, account_data)
131 | 
132 |     def get_tags(self):
133 |         return self.client.api.get_user_tags(self.client.user_id, self.room_id)
134 | 
135 |     def remove_tag(self, tag):
136 |         return self.client.api.remove_user_tag(
137 |             self.client.user_id, self.room_id, tag
138 |         )
139 | 
140 |     def add_tag(self, tag, order=None, content=None):
141 |         return self.client.api.add_user_tag(
142 |             self.client.user_id, self.room_id,
143 |             tag, order, content
144 |         )
145 | 
146 |     def send_emote(self, text):
147 |         """Send an emote (/me style) message to the room."""
148 |         return self.client.api.send_emote(self.room_id, text)
149 | 
150 |     def send_file(self, url, name, **fileinfo):
151 |         """Send a pre-uploaded file to the room.
152 | 
153 |         See http://matrix.org/docs/spec/r0.2.0/client_server.html#m-file for
154 |         fileinfo.
155 | 
156 |         Args:
157 |             url (str): The mxc url of the file.
158 |             name (str): The filename of the image.
159 |             fileinfo (): Extra information about the file
160 |         """
161 | 
162 |         return self.client.api.send_content(
163 |             self.room_id, url, name, "m.file",
164 |             extra_information=fileinfo
165 |         )
166 | 
167 |     def send_notice(self, text):
168 |         """Send a notice (from bot) message to the room."""
169 |         return self.client.api.send_notice(self.room_id, text)
170 | 
171 |     # See http://matrix.org/docs/spec/r0.0.1/client_server.html#m-image for the
172 |     # imageinfo args.
173 |     def send_image(self, url, name, **imageinfo):
174 |         """Send a pre-uploaded image to the room.
175 | 
176 |         See http://matrix.org/docs/spec/r0.0.1/client_server.html#m-image
177 |         for imageinfo
178 | 
179 |         Args:
180 |             url (str): The mxc url of the image.
181 |             name (str): The filename of the image.
182 |             imageinfo (): Extra information about the image.
183 |         """
184 |         return self.client.api.send_content(
185 |             self.room_id, url, name, "m.image",
186 |             extra_information=imageinfo
187 |         )
188 | 
189 |     def send_location(self, geo_uri, name, thumb_url=None, **thumb_info):
190 |         """Send a location to the room.
191 | 
192 |         See http://matrix.org/docs/spec/client_server/r0.2.0.html#m-location
193 |         for thumb_info
194 | 
195 |         Args:
196 |             geo_uri (str): The geo uri representing the location.
197 |             name (str): Description for the location.
198 |             thumb_url (str): URL to the thumbnail of the location.
199 |             thumb_info (): Metadata about the thumbnail, type ImageInfo.
200 |         """
201 |         return self.client.api.send_location(self.room_id, geo_uri, name,
202 |                                              thumb_url, thumb_info)
203 | 
204 |     def send_video(self, url, name, **videoinfo):
205 |         """Send a pre-uploaded video to the room.
206 | 
207 |         See http://matrix.org/docs/spec/client_server/r0.2.0.html#m-video
208 |         for videoinfo
209 | 
210 |         Args:
211 |             url (str): The mxc url of the video.
212 |             name (str): The filename of the video.
213 |             videoinfo (): Extra information about the video.
214 |         """
215 |         return self.client.api.send_content(self.room_id, url, name, "m.video",
216 |                                             extra_information=videoinfo)
217 | 
218 |     def send_audio(self, url, name, **audioinfo):
219 |         """Send a pre-uploaded audio to the room.
220 | 
221 |         See http://matrix.org/docs/spec/client_server/r0.2.0.html#m-audio
222 |         for audioinfo
223 | 
224 |         Args:
225 |             url (str): The mxc url of the audio.
226 |             name (str): The filename of the audio.
227 |             audioinfo (): Extra information about the audio.
228 |         """
229 |         return self.client.api.send_content(self.room_id, url, name, "m.audio",
230 |                                             extra_information=audioinfo)
231 | 
232 |     def redact_message(self, event_id, reason=None):
233 |         """Redacts the message with specified event_id for the given reason.
234 | 
235 |         See https://matrix.org/docs/spec/r0.0.1/client_server.html#id112
236 |         """
237 |         return self.client.api.redact_event(self.room_id, event_id, reason)
238 | 
239 |     def add_listener(self, callback, event_type=None):
240 |         """Add a callback handler for events going to this room.
241 | 
242 |         Args:
243 |             callback (func(room, event)): Callback called when an event arrives.
244 |             event_type (str): The event_type to filter for.
245 |         Returns:
246 |             uuid.UUID: Unique id of the listener, can be used to identify the listener.
247 |         """
248 |         listener_id = uuid4()
249 |         self.listeners.append(
250 |             {
251 |                 'uid': listener_id,
252 |                 'callback': callback,
253 |                 'event_type': event_type
254 |             }
255 |         )
256 |         return listener_id
257 | 
258 |     def remove_listener(self, uid):
259 |         """Remove listener with given uid."""
260 |         self.listeners[:] = (listener for listener in self.listeners
261 |                              if listener['uid'] != uid)
262 | 
263 |     def add_ephemeral_listener(self, callback, event_type=None):
264 |         """Add a callback handler for ephemeral events going to this room.
265 | 
266 |         Args:
267 |             callback (func(room, event)): Callback called when an ephemeral event arrives.
268 |             event_type (str): The event_type to filter for.
269 |         Returns:
270 |             uuid.UUID: Unique id of the listener, can be used to identify the listener.
271 |         """
272 |         listener_id = uuid4()
273 |         self.ephemeral_listeners.append(
274 |             {
275 |                 'uid': listener_id,
276 |                 'callback': callback,
277 |                 'event_type': event_type
278 |             }
279 |         )
280 |         return listener_id
281 | 
282 |     def remove_ephemeral_listener(self, uid):
283 |         """Remove ephemeral listener with given uid."""
284 |         self.ephemeral_listeners[:] = (listener for listener in self.ephemeral_listeners
285 |                                        if listener['uid'] != uid)
286 | 
287 |     def add_state_listener(self, callback, event_type=None):
288 |         """Add a callback handler for state events going to this room.
289 | 
290 |         Args:
291 |             callback (func(roomchunk)): Callback called when an event arrives.
292 |             event_type (str): The event_type to filter for.
293 |         """
294 |         self.state_listeners.append(
295 |             {
296 |                 'callback': callback,
297 |                 'event_type': event_type
298 |             }
299 |         )
300 | 
301 |     def _put_event(self, event):
302 |         self.events.append(event)
303 |         if len(self.events) > self.event_history_limit:
304 |             self.events.pop(0)
305 |         if 'state_key' in event:
306 |             self._process_state_event(event)
307 | 
308 |         # Dispatch for room-specific listeners
309 |         for listener in self.listeners:
310 |             if listener['event_type'] is None or listener['event_type'] == event['type']:
311 |                 listener['callback'](self, event)
312 | 
313 |     def _put_ephemeral_event(self, event):
314 |         # Dispatch for room-specific listeners
315 |         for listener in self.ephemeral_listeners:
316 |             if listener['event_type'] is None or listener['event_type'] == event['type']:
317 |                 listener['callback'](self, event)
318 | 
319 |     def get_events(self):
320 |         """Get the most recent events for this room."""
321 |         return self.events
322 | 
323 |     def invite_user(self, user_id):
324 |         """Invite a user to this room.
325 | 
326 |         Returns:
327 |             boolean: Whether invitation was sent.
328 |         """
329 |         try:
330 |             self.client.api.invite_user(self.room_id, user_id)
331 |             return True
332 |         except MatrixRequestError:
333 |             return False
334 | 
335 |     def kick_user(self, user_id, reason=""):
336 |         """Kick a user from this room.
337 | 
338 | 
339 |         Args:
340 |             user_id (str): The matrix user id of a user.
341 |             reason  (str): A reason for kicking the user.
342 | 
343 |         Returns:
344 |             boolean: Whether user was kicked.
345 |         """
346 |         try:
347 |             self.client.api.kick_user(self.room_id, user_id)
348 |             return True
349 |         except MatrixRequestError:
350 |             return False
351 | 
352 |     def ban_user(self, user_id, reason):
353 |         """Ban a user from this room
354 | 
355 |         Args:
356 |             user_id (str): The matrix user id of a user.
357 |             reason  (str): A reason for banning the user.
358 | 
359 |         Returns:
360 |             boolean: The user was banned.
361 |         """
362 |         try:
363 |             self.client.api.ban_user(self.room_id, user_id, reason)
364 |             return True
365 |         except MatrixRequestError:
366 |             return False
367 | 
368 |     def unban_user(self, user_id):
369 |         """Unban a user from this room
370 | 
371 |         Returns:
372 |             boolean: The user was unbanned.
373 |         """
374 |         try:
375 |             self.client.api.unban_user(self.room_id, user_id)
376 |             return True
377 |         except MatrixRequestError:
378 |             return False
379 | 
380 |     def leave(self):
381 |         """Leave the room.
382 | 
383 |         Returns:
384 |             boolean: Leaving the room was successful.
385 |         """
386 |         try:
387 |             self.client.api.leave_room(self.room_id)
388 |             del self.client.rooms[self.room_id]
389 |             return True
390 |         except MatrixRequestError:
391 |             return False
392 | 
393 |     def update_room_name(self):
394 |         """Updates self.name and returns True if room name has changed."""
395 |         try:
396 |             response = self.client.api.get_room_name(self.room_id)
397 |             if "name" in response and response["name"] != self.name:
398 |                 self.name = response["name"]
399 |                 return True
400 |             else:
401 |                 return False
402 |         except MatrixRequestError:
403 |             return False
404 | 
405 |     def set_room_name(self, name):
406 |         """Return True if room name successfully changed."""
407 |         try:
408 |             self.client.api.set_room_name(self.room_id, name)
409 |             self.name = name
410 |             return True
411 |         except MatrixRequestError:
412 |             return False
413 | 
414 |     def send_state_event(self, event_type, content, state_key=""):
415 |         """Send a state event to the room.
416 | 
417 |         Args:
418 |             event_type (str): The type of event that you are sending.
419 |             content (): An object with the content of the message.
420 |             state_key (str, optional): A unique key to identify the state.
421 |         """
422 |         return self.client.api.send_state_event(
423 |             self.room_id,
424 |             event_type,
425 |             content,
426 |             state_key
427 |         )
428 | 
429 |     def update_room_topic(self):
430 |         """Updates self.topic and returns True if room topic has changed."""
431 |         try:
432 |             response = self.client.api.get_room_topic(self.room_id)
433 |             if "topic" in response and response["topic"] != self.topic:
434 |                 self.topic = response["topic"]
435 |                 return True
436 |             else:
437 |                 return False
438 |         except MatrixRequestError:
439 |             return False
440 | 
441 |     def set_room_topic(self, topic):
442 |         """Set room topic.
443 | 
444 |         Returns:
445 |             boolean: True if the topic changed, False if not
446 |         """
447 |         try:
448 |             self.client.api.set_room_topic(self.room_id, topic)
449 |             self.topic = topic
450 |             return True
451 |         except MatrixRequestError:
452 |             return False
453 | 
454 |     def update_aliases(self):
455 |         """Get aliases information from room state.
456 | 
457 |         Returns:
458 |             boolean: True if the aliases changed, False if not
459 |         """
460 |         try:
461 |             response = self.client.api.get_room_state(self.room_id)
462 |             for chunk in response:
463 |                 if "content" in chunk and "aliases" in chunk["content"]:
464 |                     if chunk["content"]["aliases"] != self.aliases:
465 |                         self.aliases = chunk["content"]["aliases"]
466 |                         return True
467 |                     else:
468 |                         return False
469 |         except MatrixRequestError:
470 |             return False
471 | 
472 |     def add_room_alias(self, room_alias):
473 |         """Add an alias to the room and return True if successful."""
474 |         try:
475 |             self.client.api.set_room_alias(self.room_id, room_alias)
476 |             return True
477 |         except MatrixRequestError:
478 |             return False
479 | 
480 |     def get_joined_members(self):
481 |         """Returns list of joined members (User objects)."""
482 |         if self._members:
483 |             return list(self._members.values())
484 |         response = self.client.api.get_room_members(self.room_id)
485 |         for event in response["chunk"]:
486 |             if event["content"]["membership"] == "join":
487 |                 user_id = event["state_key"]
488 |                 self._add_member(user_id, event["content"].get("displayname"))
489 |         return list(self._members.values())
490 | 
491 |     def _add_member(self, user_id, displayname=None):
492 |         if displayname:
493 |             self.members_displaynames[user_id] = displayname
494 |         if user_id in self._members:
495 |             return
496 |         if user_id in self.client.users:
497 |             self._members[user_id] = self.client.users[user_id]
498 |             return
499 |         self._members[user_id] = User(self.client.api, user_id, displayname)
500 |         self.client.users[user_id] = self._members[user_id]
501 | 
502 |     def backfill_previous_messages(self, reverse=False, limit=10):
503 |         """Backfill handling of previous messages.
504 | 
505 |         Args:
506 |             reverse (bool): When false messages will be backfilled in their original
507 |                 order (old to new), otherwise the order will be reversed (new to old).
508 |             limit (int): Number of messages to go back.
509 |         """
510 |         res = self.client.api.get_room_messages(self.room_id, self.prev_batch,
511 |                                                 direction="b", limit=limit)
512 |         events = res["chunk"]
513 |         if not reverse:
514 |             events = reversed(events)
515 |         for event in events:
516 |             self._put_event(event)
517 | 
518 |     def modify_user_power_levels(self, users=None, users_default=None):
519 |         """Modify the power level for a subset of users
520 | 
521 |         Args:
522 |             users(dict): Power levels to assign to specific users, in the form
523 |                 {"@name0:host0": 10, "@name1:host1": 100, "@name3:host3", None}
524 |                 A level of None causes the user to revert to the default level
525 |                 as specified by users_default.
526 |             users_default(int): Default power level for users in the room
527 | 
528 |         Returns:
529 |             True if successful, False if not
530 |         """
531 |         try:
532 |             content = self.client.api.get_power_levels(self.room_id)
533 |             if users_default:
534 |                 content["users_default"] = users_default
535 | 
536 |             if users:
537 |                 if "users" in content:
538 |                     content["users"].update(users)
539 |                 else:
540 |                     content["users"] = users
541 | 
542 |                 # Remove any keys with value None
543 |                 for user, power_level in list(content["users"].items()):
544 |                     if power_level is None:
545 |                         del content["users"][user]
546 |             self.client.api.set_power_levels(self.room_id, content)
547 |             return True
548 |         except MatrixRequestError:
549 |             return False
550 | 
551 |     def modify_required_power_levels(self, events=None, **kwargs):
552 |         """Modifies room power level requirements.
553 | 
554 |         Args:
555 |             events(dict): Power levels required for sending specific event types,
556 |                 in the form {"m.room.whatever0": 60, "m.room.whatever2": None}.
557 |                 Overrides events_default and state_default for the specified
558 |                 events. A level of None causes the target event to revert to the
559 |                 default level as specified by events_default or state_default.
560 |             **kwargs: Key/value pairs specifying the power levels required for
561 |                     various actions:
562 | 
563 |                     - events_default(int): Default level for sending message events
564 |                     - state_default(int): Default level for sending state events
565 |                     - invite(int): Inviting a user
566 |                     - redact(int): Redacting an event
567 |                     - ban(int): Banning a user
568 |                     - kick(int): Kicking a user
569 | 
570 |         Returns:
571 |             True if successful, False if not
572 |         """
573 |         try:
574 |             content = self.client.api.get_power_levels(self.room_id)
575 |             content.update(kwargs)
576 |             for key, value in list(content.items()):
577 |                 if value is None:
578 |                     del content[key]
579 | 
580 |             if events:
581 |                 if "events" in content:
582 |                     content["events"].update(events)
583 |                 else:
584 |                     content["events"] = events
585 | 
586 |                 # Remove any keys with value None
587 |                 for event, power_level in list(content["events"].items()):
588 |                     if power_level is None:
589 |                         del content["events"][event]
590 | 
591 |             self.client.api.set_power_levels(self.room_id, content)
592 |             return True
593 |         except MatrixRequestError:
594 |             return False
595 | 
596 |     def set_invite_only(self, invite_only):
597 |         """Set how the room can be joined.
598 | 
599 |         Args:
600 |             invite_only(bool): If True, users will have to be invited to join
601 |                 the room. If False, anyone who knows the room link can join.
602 | 
603 |         Returns:
604 |             True if successful, False if not
605 |         """
606 |         join_rule = "invite" if invite_only else "public"
607 |         try:
608 |             self.client.api.set_join_rule(self.room_id, join_rule)
609 |             self.invite_only = invite_only
610 |             return True
611 |         except MatrixRequestError:
612 |             return False
613 | 
614 |     def set_guest_access(self, allow_guests):
615 |         """Set whether guests can join the room and return True if successful."""
616 |         guest_access = "can_join" if allow_guests else "forbidden"
617 |         try:
618 |             self.client.api.set_guest_access(self.room_id, guest_access)
619 |             self.guest_access = allow_guests
620 |             return True
621 |         except MatrixRequestError:
622 |             return False
623 | 
624 |     def enable_encryption(self):
625 |         """Enables encryption in the room.
626 | 
627 |         NOTE: Once enabled, encryption cannot be disabled.
628 | 
629 |         Returns:
630 |         True if successful, False if not
631 |         """
632 |         try:
633 |             self.send_state_event("m.room.encryption",
634 |                                   {"algorithm": "m.megolm.v1.aes-sha2"})
635 |             self.encrypted = True
636 |             return True
637 |         except MatrixRequestError:
638 |             return False
639 | 
640 |     def _process_state_event(self, state_event):
641 |         if "type" not in state_event:
642 |             return  # Ignore event
643 |         etype = state_event["type"]
644 |         econtent = state_event["content"]
645 |         clevel = self.client._cache_level
646 | 
647 |         # Don't keep track of room state if caching turned off
648 |         if clevel >= 0:
649 |             try:
650 |                 if etype == "m.room.name":
651 |                     self.name = econtent.get("name")
652 |                 elif etype == "m.room.canonical_alias":
653 |                     self.canonical_alias = econtent.get("alias")
654 |                 elif etype == "m.room.topic":
655 |                     self.topic = econtent.get("topic")
656 |                 elif etype == "m.room.aliases":
657 |                     self.aliases = econtent.get("aliases")
658 |                 elif etype == "m.room.join_rules":
659 |                     self.invite_only = econtent["join_rule"] == "invite"
660 |                 elif etype == "m.room.guest_access":
661 |                     self.guest_access = econtent["guest_access"] == "can_join"
662 |                 elif etype == "m.room.encryption":
663 |                     if econtent.get("algorithm") == "m.megolm.v1.aes-sha2":
664 |                         self.encrypted = True
665 |                 elif etype == "m.room.member" and clevel == clevel.ALL:
666 |                     # tracking room members can be large e.g. #matrix:matrix.org
667 |                     if econtent["membership"] == "join":
668 |                         user_id = state_event["state_key"]
669 |                         self._add_member(user_id, econtent.get("displayname"))
670 |                     elif econtent["membership"] in ("leave", "kick", "invite"):
671 |                         self._members.pop(state_event["state_key"], None)
672 |             except KeyError:
673 |                 logger.exception("Unable to parse state event %s, passing over.",
674 |                                  state_event['event_id'])
675 | 
676 |         for listener in self.state_listeners:
677 |             if (
678 |                 listener['event_type'] is None or
679 |                 listener['event_type'] == state_event['type']
680 |             ):
681 |                 listener['callback'](state_event)
682 | 
683 |     @property
684 |     def prev_batch(self):
685 |         return self._prev_batch
686 | 
687 |     @prev_batch.setter
688 |     def prev_batch(self, prev_batch):
689 |         self._prev_batch = prev_batch
690 | 


--------------------------------------------------------------------------------
/matrix_client/user.py:
--------------------------------------------------------------------------------
 1 | # -*- coding: utf-8 -*-
 2 | # Copyright 2015 OpenMarket Ltd
 3 | #
 4 | # Licensed under the Apache License, Version 2.0 (the "License");
 5 | # you may not use this file except in compliance with the License.
 6 | # You may obtain a copy of the License at
 7 | #
 8 | #     http://www.apache.org/licenses/LICENSE-2.0
 9 | #
10 | # Unless required by applicable law or agreed to in writing, software
11 | # distributed under the License is distributed on an "AS IS" BASIS,
12 | # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
13 | # See the License for the specific language governing permissions and
14 | # limitations under the License.
15 | from warnings import warn
16 | 
17 | from .checks import check_user_id
18 | 
19 | 
20 | class User(object):
21 |     """ The User class can be used to call user specific functions.
22 |     """
23 |     def __init__(self, api, user_id, displayname=None):
24 |         check_user_id(user_id)
25 | 
26 |         self.user_id = user_id
27 |         self.displayname = displayname
28 |         self.api = api
29 | 
30 |     def get_display_name(self, room=None):
31 |         """Get this user's display name.
32 | 
33 |         Args:
34 |             room (Room): Optional. When specified, return the display name of the user
35 |                 in this room.
36 | 
37 |         Returns:
38 |             The display name. Defaults to the user ID if not set.
39 |         """
40 |         if room:
41 |             try:
42 |                 return room.members_displaynames[self.user_id]
43 |             except KeyError:
44 |                 return self.user_id
45 |         if not self.displayname:
46 |             self.displayname = self.api.get_display_name(self.user_id)
47 |         return self.displayname or self.user_id
48 | 
49 |     def get_friendly_name(self):
50 |         """Deprecated. Use :meth:`get_display_name` instead."""
51 |         warn("get_friendly_name is deprecated. Use get_display_name instead.",
52 |              DeprecationWarning)
53 |         return self.get_display_name()
54 | 
55 |     def set_display_name(self, display_name):
56 |         """ Set this users display name.
57 | 
58 |         Args:
59 |             display_name (str): Display Name
60 |         """
61 |         self.displayname = display_name
62 |         return self.api.set_display_name(self.user_id, display_name)
63 | 
64 |     def get_avatar_url(self):
65 |         mxcurl = self.api.get_avatar_url(self.user_id)
66 |         url = None
67 |         if mxcurl is not None:
68 |             url = self.api.get_download_url(mxcurl)
69 |         return url
70 | 
71 |     def set_avatar_url(self, avatar_url):
72 |         """ Set this users avatar.
73 | 
74 |         Args:
75 |             avatar_url (str): mxc url from previously uploaded
76 |         """
77 |         return self.api.set_avatar_url(self.user_id, avatar_url)
78 | 


--------------------------------------------------------------------------------
/samples/ChangeDisplayName.py:
--------------------------------------------------------------------------------
 1 | #!/usr/bin/env python3
 2 | 
 3 | # Set the current users display name.
 4 | # Args: host:port username password display_name
 5 | # Error Codes:
 6 | # 2 - Could not find the server.
 7 | # 3 - Bad URL Format.
 8 | # 4 - Bad username/password.
 9 | # 11 - Serverside Error
10 | 
11 | import sys
12 | import samples_common
13 | 
14 | from matrix_client.client import MatrixClient
15 | from matrix_client.api import MatrixRequestError
16 | from matrix_client.user import User
17 | from requests.exceptions import MissingSchema
18 | 
19 | 
20 | host, username, password = samples_common.get_user_details(sys.argv)
21 | 
22 | client = MatrixClient(host)
23 | 
24 | try:
25 |     client.login(username, password)
26 | except MatrixRequestError as e:
27 |     print(e)
28 |     if e.code == 403:
29 |         print("Bad username or password.")
30 |         sys.exit(4)
31 |     else:
32 |         print("Check your server details are correct.")
33 |         sys.exit(2)
34 | except MissingSchema as e:
35 |     print("Bad URL format.")
36 |     print(e)
37 |     sys.exit(3)
38 | 
39 | user = User(client.api, client.user_id)
40 | 
41 | if len(sys.argv) < 5:
42 |     print("Current Display Name: %s" % user.get_display_name())
43 | 
44 |     displayname = input("New Display Name: ")
45 | else:
46 |     displayname = sys.argv[4]
47 | 
48 | try:
49 |     user.set_display_name(displayname)
50 | except MatrixRequestError as e:
51 |     print(e)
52 |     sys.exit(11)
53 | 


--------------------------------------------------------------------------------
/samples/GetUserProfile.py:
--------------------------------------------------------------------------------
 1 | #!/usr/bin/env python3
 2 | 
 3 | # Get a users display name and avatar
 4 | # Args: host:port username password user_id
 5 | # Error Codes:
 6 | # 2 - Could not find the server.
 7 | # 3 - Bad URL Format.
 8 | # 4 - Bad username/password.
 9 | 
10 | 
11 | import sys
12 | import samples_common  # Common bits used between samples
13 | 
14 | from matrix_client.client import MatrixClient
15 | from matrix_client.api import MatrixRequestError
16 | from requests.exceptions import MissingSchema
17 | 
18 | host, username, password = samples_common.get_user_details(sys.argv)
19 | 
20 | client = MatrixClient(host)
21 | 
22 | try:
23 |     client.login(username, password)
24 | except MatrixRequestError as e:
25 |     print(e)
26 |     if e.code == 403:
27 |         print("Bad username or password.")
28 |         sys.exit(4)
29 |     else:
30 |         print("Check your server details are correct.")
31 |         sys.exit(2)
32 | except MissingSchema as e:
33 |     print("Bad URL format.")
34 |     print(e)
35 |     sys.exit(3)
36 | 
37 | if len(sys.argv) > 4:
38 |     userid = sys.argv[4]
39 | else:
40 |     userid = samples_common.get_input("UserID: ")
41 | 
42 | try:
43 |     user = client.get_user(userid)
44 |     print("Display Name: %s" % user.get_display_name())
45 |     print("Avatar %s" % user.get_avatar_url())
46 | except MatrixRequestError as e:
47 |     print(e)
48 |     if e.code == 400:
49 |         print("User ID/Alias in the wrong format")
50 |         sys.exit(11)
51 |     else:
52 |         print("Couldn't find room.")
53 |         sys.exit(12)
54 | 


--------------------------------------------------------------------------------
/samples/SetRoomProfile.py:
--------------------------------------------------------------------------------
 1 | #!/usr/bin/env python3
 2 | 
 3 | # Set a profile for a room.
 4 | # Args: host:port username password
 5 | # Error Codes:
 6 | # 2 - Could not find the server.
 7 | # 3 - Bad URL Format.
 8 | # 4 - Bad username/password.
 9 | # 11 - Serverside Error
10 | 
11 | import sys
12 | import samples_common
13 | 
14 | from matrix_client.client import MatrixClient
15 | from matrix_client.api import MatrixRequestError
16 | from requests.exceptions import MissingSchema
17 | 
18 | 
19 | host, username, password = samples_common.get_user_details(sys.argv)
20 | 
21 | client = MatrixClient(host)
22 | 
23 | try:
24 |     client.login(username, password, sync=False)
25 | except MatrixRequestError as e:
26 |     print(e)
27 |     if e.code == 403:
28 |         print("Bad username or password.")
29 |         sys.exit(4)
30 |     else:
31 |         print("Check your server details are correct.")
32 |         sys.exit(2)
33 | except MissingSchema as e:
34 |     print("Bad URL format.")
35 |     print(e)
36 |     sys.exit(3)
37 | 
38 | room = client.join_room(input("Room:"))
39 | displayname = input("Displayname:")
40 | if len(displayname) == 0:
41 |     print("Not setting displayname")
42 |     displayname = None
43 | 
44 | avatar = input("Avatar:")
45 | if len(avatar) == 0:
46 |     print("Not setting avatar")
47 |     avatar = None
48 | 
49 | try:
50 |     room.set_user_profile(displayname, avatar)
51 | except MatrixRequestError as e:
52 |     print(e)
53 |     sys.exit(11)
54 | 


--------------------------------------------------------------------------------
/samples/SimpleChatClient.py:
--------------------------------------------------------------------------------
 1 | #!/usr/bin/env python3
 2 | 
 3 | # A simple chat client for matrix.
 4 | # This sample will allow you to connect to a room, and send/recieve messages.
 5 | # Args: host:port username password room
 6 | # Error Codes:
 7 | # 1 - Unknown problem has occured
 8 | # 2 - Could not find the server.
 9 | # 3 - Bad URL Format.
10 | # 4 - Bad username/password.
11 | # 11 - Wrong room format.
12 | # 12 - Couldn't find room.
13 | 
14 | import sys
15 | import samples_common  # Common bits used between samples
16 | import logging
17 | 
18 | from matrix_client.client import MatrixClient
19 | from matrix_client.api import MatrixRequestError
20 | from requests.exceptions import MissingSchema
21 | 
22 | 
23 | # Called when a message is recieved.
24 | def on_message(room, event):
25 |     if event['type'] == "m.room.member":
26 |         if event['membership'] == "join":
27 |             print("{0} joined".format(event['content']['displayname']))
28 |     elif event['type'] == "m.room.message":
29 |         if event['content']['msgtype'] == "m.text":
30 |             print("{0}: {1}".format(event['sender'], event['content']['body']))
31 |     else:
32 |         print(event['type'])
33 | 
34 | 
35 | def main(host, username, password, room_id_alias):
36 |     client = MatrixClient(host)
37 | 
38 |     try:
39 |         client.login(username, password)
40 |     except MatrixRequestError as e:
41 |         print(e)
42 |         if e.code == 403:
43 |             print("Bad username or password.")
44 |             sys.exit(4)
45 |         else:
46 |             print("Check your sever details are correct.")
47 |             sys.exit(2)
48 |     except MissingSchema as e:
49 |         print("Bad URL format.")
50 |         print(e)
51 |         sys.exit(3)
52 | 
53 |     try:
54 |         room = client.join_room(room_id_alias)
55 |     except MatrixRequestError as e:
56 |         print(e)
57 |         if e.code == 400:
58 |             print("Room ID/Alias in the wrong format")
59 |             sys.exit(11)
60 |         else:
61 |             print("Couldn't find room.")
62 |             sys.exit(12)
63 | 
64 |     room.add_listener(on_message)
65 |     client.start_listener_thread()
66 | 
67 |     while True:
68 |         msg = samples_common.get_input()
69 |         if msg == "/quit":
70 |             break
71 |         else:
72 |             room.send_text(msg)
73 | 
74 | 
75 | if __name__ == '__main__':
76 |     logging.basicConfig(level=logging.WARNING)
77 |     host, username, password = samples_common.get_user_details(sys.argv)
78 | 
79 |     if len(sys.argv) > 4:
80 |         room_id_alias = sys.argv[4]
81 |     else:
82 |         room_id_alias = samples_common.get_input("Room ID/Alias: ")
83 | 
84 |     main(host, username, password, room_id_alias)
85 | 


--------------------------------------------------------------------------------
/samples/UserPassOrTokenClient.py:
--------------------------------------------------------------------------------
 1 | #!/usr/bin/env python3
 2 | """
 3 | Get a users room list and indicate login type.
 4 | 
 5 | to use user+pass to login and get a token:
 6 |     arg usage: --host 'host' --user 'username' --password 'password'
 7 | to use user+token to login:
 8 |     arg usage: --host 'host' --user 'username' --token 'token'
 9 | Error Codes:
10 | 1 - No password or token given (can't login)
11 | 2 - Combination of user + pass is incorrect/invalid
12 | 3 - Combination of user + token is incorrect/invalid
13 | 4 - Server details invalid/incorrect
14 | 5 - Malformed URL for connection
15 | 6 - Invalid URL schema
16 | """
17 | 
18 | import argparse
19 | from matrix_client.client import MatrixClient
20 | from matrix_client.api import MatrixRequestError
21 | from requests.exceptions import MissingSchema, InvalidSchema
22 | 
23 | 
24 | def example(host, user, password, token):
25 |     """run the example."""
26 |     client = None
27 |     try:
28 |         if token:
29 |             print('token login')
30 |             client = MatrixClient(host, token=token)
31 |         else:
32 |             print('password login')
33 |             client = MatrixClient(host)
34 |             token = client.login(user, password)
35 |             print('got token: %s' % token)
36 |     except MatrixRequestError as e:
37 |         print(e)
38 |         if e.code == 403:
39 |             print("Bad username or password")
40 |             exit(2)
41 |         elif e.code == 401:
42 |             print("Bad username or token")
43 |             exit(3)
44 |         else:
45 |             print("Verify server details.")
46 |             exit(4)
47 |     except MissingSchema as e:
48 |         print(e)
49 |         print("Bad formatting of URL.")
50 |         exit(5)
51 |     except InvalidSchema as e:
52 |         print(e)
53 |         print("Invalid URL schema")
54 |         exit(6)
55 |     print("is in rooms")
56 |     for room_id, room in client.get_rooms().items():
57 |         print(room_id)
58 | 
59 | 
60 | def main():
61 |     """Main entry."""
62 |     parser = argparse.ArgumentParser()
63 |     parser.add_argument("--host", type=str, required=True)
64 |     parser.add_argument("--user", type=str, required=True)
65 |     parser.add_argument("--password", type=str)
66 |     parser.add_argument("--token", type=str)
67 |     args = parser.parse_args()
68 |     if not args.password and not args.token:
69 |         print('password or token is required')
70 |         exit(1)
71 |     example(args.host, args.user, args.password, args.token)
72 | 
73 | 
74 | if __name__ == "__main__":
75 |     main()
76 | 


--------------------------------------------------------------------------------
/samples/samples_common.py:
--------------------------------------------------------------------------------
 1 | # Common functions for sample code.
 2 | 
 3 | from getpass import getpass
 4 | 
 5 | try:
 6 |     get_input = raw_input
 7 | except NameError:
 8 |     get_input = input
 9 | 
10 | 
11 | def get_user_details(argv):
12 |     try:
13 |         host = argv[1]
14 |     except IndexError:
15 |         host = get_input("Host (ex: http://localhost:8008 ): ")
16 | 
17 |     try:
18 |         username = argv[2]
19 |     except IndexError:
20 |         username = get_input("Username: ")
21 | 
22 |     try:
23 |         password = argv[3]
24 |     except IndexError:
25 |         password = getpass()  # Hide user input
26 | 
27 |     return host, username, password
28 | 


--------------------------------------------------------------------------------
/setup.cfg:
--------------------------------------------------------------------------------
 1 | [flake8]
 2 | max-line-length = 90
 3 | 
 4 | [pep8]
 5 | max-line-length = 90
 6 | 
 7 | [aliases]
 8 | test=pytest
 9 | 
10 | [tool:pytest]
11 | addopts = test/
12 | 
13 | [bdist_wheel]
14 | universal = 1
15 | 
16 | [metadata]
17 | license_file = LICENSE


--------------------------------------------------------------------------------
/setup.py:
--------------------------------------------------------------------------------
 1 | #!/usr/bin/env python
 2 | from setuptools import setup, find_packages
 3 | import codecs
 4 | import os
 5 | 
 6 | here = os.path.abspath(os.path.dirname(__file__))
 7 | 
 8 | 
 9 | def read_file(names, encoding='utf-8'):
10 |     file_path = os.path.join(here, *names)
11 |     if encoding:
12 |         with codecs.open(file_path, encoding=encoding) as f:
13 |             return f.read()
14 |     else:
15 |         with open(file_path, 'rb') as f:
16 |             return f.read()
17 | 
18 | 
19 | def exec_file(names):
20 |     code = read_file(names, encoding=None)
21 |     result = {}
22 |     exec(code, result)
23 |     return result
24 | 
25 | 
26 | setup(
27 |     name='matrix_client',
28 |     version=exec_file(('matrix_client', '__init__.py',))['__version__'],
29 |     description='Client-Server SDK for Matrix',
30 |     long_description=read_file(('README.rst',)),
31 |     long_description_content_type="text/x-rst",
32 |     author='The Matrix.org Team',
33 |     author_email='team@matrix.org',
34 |     url='https://github.com/matrix-org/matrix-python-sdk',
35 |     packages=find_packages(),
36 |     license='Apache License, Version 2.0',
37 |     classifiers=[
38 |         'Development Status :: 3 - Alpha',
39 |         'Intended Audience :: Developers',
40 |         'License :: OSI Approved :: Apache Software License',
41 |         'Programming Language :: Python :: 2',
42 |         'Programming Language :: Python :: 3',
43 |         'Topic :: Communications :: Chat',
44 |         'Topic :: Communications :: Conferencing',
45 |     ],
46 |     keywords='chat sdk matrix matrix.org',
47 |     install_requires=[
48 |         'requests~=2.22',
49 |         'urllib3~=1.21',
50 |     ],
51 |     setup_requires=['pytest-runner~=5.1'],
52 |     tests_require=['pytest >=4.6.5, <6.0.0', 'responses >=0.10.6, ==0.10.*'],
53 |     extras_require={
54 |         'test': ['pytest >=4.6, <6.0.0', 'responses >=0.10.6, ==0.10.*'],
55 |         'doc': ['Sphinx >=1.7.6, ==1.*', 'sphinx-rtd-theme >=0.1.9, ==0.1.*',
56 |                 'sphinxcontrib-napoleon >=0.5.3, ==0.5.*'],
57 |         'e2e': ['python-olm~=3.1', 'canonicaljson~=1.1']
58 |     },
59 | )
60 | 


--------------------------------------------------------------------------------
/test/__init__.py:
--------------------------------------------------------------------------------
https://raw.githubusercontent.com/matrix-org/matrix-python-sdk/887f5d55e16518a0a2bef4f2d6bff6ecf48d18c1/test/__init__.py


--------------------------------------------------------------------------------
/test/api_test.py:
--------------------------------------------------------------------------------
  1 | import responses
  2 | import pytest
  3 | import json
  4 | from copy import deepcopy
  5 | from matrix_client import client, api
  6 | from matrix_client.errors import MatrixRequestError, MatrixError, MatrixHttpLibError
  7 | from matrix_client import __version__ as lib_version
  8 | from . import response_examples
  9 | MATRIX_V2_API_PATH = "/_matrix/client/r0"
 10 | 
 11 | 
 12 | class TestTagsApi:
 13 |     cli = client.MatrixClient("http://example.com")
 14 |     user_id = "@user:matrix.org"
 15 |     room_id = "#foo:matrix.org"
 16 | 
 17 |     @responses.activate
 18 |     def test_get_user_tags(self):
 19 |         tags_url = "http://example.com" \
 20 |             "/_matrix/client/r0/user/@user:matrix.org/rooms/#foo:matrix.org/tags"
 21 |         responses.add(responses.GET, tags_url, body='{}')
 22 |         self.cli.api.get_user_tags(self.user_id, self.room_id)
 23 |         req = responses.calls[0].request
 24 |         assert req.url == tags_url
 25 |         assert req.method == 'GET'
 26 | 
 27 |     @responses.activate
 28 |     def test_add_user_tags(self):
 29 |         tags_url = "http://example.com" \
 30 |             "/_matrix/client/r0/user/@user:matrix.org/rooms/#foo:matrix.org/tags/foo"
 31 |         responses.add(responses.PUT, tags_url, body='{}')
 32 |         self.cli.api.add_user_tag(self.user_id, self.room_id, "foo", body={"order": "5"})
 33 |         req = responses.calls[0].request
 34 |         assert req.url == tags_url
 35 |         assert req.method == 'PUT'
 36 | 
 37 |     @responses.activate
 38 |     def test_remove_user_tags(self):
 39 |         tags_url = "http://example.com" \
 40 |             "/_matrix/client/r0/user/@user:matrix.org/rooms/#foo:matrix.org/tags/foo"
 41 |         responses.add(responses.DELETE, tags_url, body='{}')
 42 |         self.cli.api.remove_user_tag(self.user_id, self.room_id, "foo")
 43 |         req = responses.calls[0].request
 44 |         assert req.url == tags_url
 45 |         assert req.method == 'DELETE'
 46 | 
 47 | 
 48 | class TestAccountDataApi:
 49 |     cli = client.MatrixClient("http://example.com")
 50 |     user_id = "@user:matrix.org"
 51 |     room_id = "#foo:matrix.org"
 52 | 
 53 |     @responses.activate
 54 |     def test_set_account_data(self):
 55 |         account_data_url = "http://example.com" \
 56 |             "/_matrix/client/r0/user/@user:matrix.org/account_data/foo"
 57 |         responses.add(responses.PUT, account_data_url, body='{}')
 58 |         self.cli.api.set_account_data(self.user_id, 'foo', {'bar': 1})
 59 |         req = responses.calls[0].request
 60 |         assert req.url == account_data_url
 61 |         assert req.method == 'PUT'
 62 | 
 63 |     @responses.activate
 64 |     def test_set_room_account_data(self):
 65 |         account_data_url = "http://example.com/_matrix/client/r0/user" \
 66 |             "/@user:matrix.org/rooms/#foo:matrix.org/account_data/foo"
 67 |         responses.add(responses.PUT, account_data_url, body='{}')
 68 |         self.cli.api.set_room_account_data(self.user_id, self.room_id, 'foo', {'bar': 1})
 69 |         req = responses.calls[0].request
 70 |         assert req.url == account_data_url
 71 |         assert req.method == 'PUT'
 72 | 
 73 | 
 74 | class TestUnbanApi:
 75 |     cli = client.MatrixClient("http://example.com")
 76 |     user_id = "@user:matrix.org"
 77 |     room_id = "#foo:matrix.org"
 78 | 
 79 |     @responses.activate
 80 |     def test_unban(self):
 81 |         unban_url = "http://example.com" \
 82 |                     "/_matrix/client/r0/rooms/#foo:matrix.org/unban"
 83 |         responses.add(responses.POST, unban_url, body='{}')
 84 |         self.cli.api.unban_user(self.room_id, self.user_id)
 85 |         req = responses.calls[0].request
 86 |         assert req.url == unban_url
 87 |         assert req.method == 'POST'
 88 | 
 89 | 
 90 | class TestDeviceApi:
 91 |     cli = client.MatrixClient("http://example.com")
 92 |     device_id = "QBUAZIFURK"
 93 |     display_name = "test_name"
 94 |     auth_body = {
 95 |         "auth": {
 96 |             "type": "example.type.foo",
 97 |             "session": "xxxxx",
 98 |             "example_credential": "verypoorsharedsecret"
 99 |         }
100 |     }
101 | 
102 |     @responses.activate
103 |     def test_get_devices(self):
104 |         get_devices_url = "http://example.com/_matrix/client/r0/devices"
105 |         responses.add(responses.GET, get_devices_url, body='{}')
106 |         self.cli.api.get_devices()
107 |         req = responses.calls[0].request
108 |         assert req.url == get_devices_url
109 |         assert req.method == 'GET'
110 | 
111 |     @responses.activate
112 |     def test_get_device(self):
113 |         get_device_url = "http://example.com/_matrix/client/r0/devices/QBUAZIFURK"
114 |         responses.add(responses.GET, get_device_url, body='{}')
115 |         self.cli.api.get_device(self.device_id)
116 |         req = responses.calls[0].request
117 |         assert req.url == get_device_url
118 |         assert req.method == 'GET'
119 | 
120 |     @responses.activate
121 |     def test_update_device_info(self):
122 |         update_url = "http://example.com/_matrix/client/r0/devices/QBUAZIFURK"
123 |         responses.add(responses.PUT, update_url, body='{}')
124 |         self.cli.api.update_device_info(self.device_id, self.display_name)
125 |         req = responses.calls[0].request
126 |         assert req.url == update_url
127 |         assert req.method == 'PUT'
128 | 
129 |     @responses.activate
130 |     def test_delete_device(self):
131 |         delete_device_url = "http://example.com/_matrix/client/r0/devices/QBUAZIFURK"
132 |         responses.add(responses.DELETE, delete_device_url, body='{}')
133 |         # Test for 401 status code of User-Interactive Auth API
134 |         responses.add(responses.DELETE, delete_device_url, body='{}', status=401)
135 |         self.cli.api.delete_device(self.auth_body, self.device_id)
136 |         req = responses.calls[0].request
137 |         assert req.url == delete_device_url
138 |         assert req.method == 'DELETE'
139 | 
140 |         with pytest.raises(MatrixRequestError):
141 |             self.cli.api.delete_device(self.auth_body, self.device_id)
142 | 
143 |     @responses.activate
144 |     def test_delete_devices(self):
145 |         delete_devices_url = "http://example.com/_matrix/client/r0/delete_devices"
146 |         responses.add(responses.POST, delete_devices_url, body='{}')
147 |         # Test for 401 status code of User-Interactive Auth API
148 |         responses.add(responses.POST, delete_devices_url, body='{}', status=401)
149 |         self.cli.api.delete_devices(self.auth_body, [self.device_id])
150 |         req = responses.calls[0].request
151 |         assert req.url == delete_devices_url
152 |         assert req.method == 'POST'
153 | 
154 |         with pytest.raises(MatrixRequestError):
155 |             self.cli.api.delete_devices(self.auth_body, [self.device_id])
156 | 
157 | 
158 | class TestKeysApi:
159 |     cli = client.MatrixClient("http://example.com")
160 |     user_id = "@alice:matrix.org"
161 |     device_id = "JLAFKJWSCS"
162 |     one_time_keys = {"curve25519:AAAAAQ": "/qyvZvwjiTxGdGU0RCguDCLeR+nmsb3FfNG3/Ve4vU8"}
163 |     device_keys = {
164 |         "user_id": "@alice:example.com",
165 |         "device_id": "JLAFKJWSCS",
166 |         "algorithms": [
167 |             "m.olm.curve25519-aes-sha256",
168 |             "m.megolm.v1.aes-sha"
169 |         ],
170 |         "keys": {
171 |             "curve25519:JLAFKJWSCS": "3C5BFWi2Y8MaVvjM8M22DBmh24PmgR0nPvJOIArzgyI",
172 |             "ed25519:JLAFKJWSCS": "lEuiRJBit0IG6nUf5pUzWTUEsRVVe/HJkoKuEww9ULI"
173 |         },
174 |         "signatures": {
175 |             "@alice:example.com": {
176 |                 "ed25519:JLAFKJWSCS": ("dSO80A01XiigH3uBiDVx/EjzaoycHcjq9lfQX0uWsqxl2gi"
177 |                                        "MIiSPR8a4d291W1ihKJL/a+myXS367WT6NAIcBA")
178 |             }
179 |         }
180 |     }
181 | 
182 |     @responses.activate
183 |     @pytest.mark.parametrize("args", [
184 |         {},
185 |         {'device_keys': device_keys},
186 |         {'one_time_keys': one_time_keys}
187 |     ])
188 |     def test_upload_keys(self, args):
189 |         upload_keys_url = "http://example.com/_matrix/client/r0/keys/upload"
190 |         responses.add(responses.POST, upload_keys_url, body='{}')
191 |         self.cli.api.upload_keys(**args)
192 |         req = responses.calls[0].request
193 |         assert req.url == upload_keys_url
194 |         assert req.method == 'POST'
195 | 
196 |     @responses.activate
197 |     def test_query_keys(self):
198 |         query_user_keys_url = "http://example.com/_matrix/client/r0/keys/query"
199 |         responses.add(responses.POST, query_user_keys_url, body='{}')
200 |         self.cli.api.query_keys({self.user_id: self.device_id}, timeout=10)
201 |         req = responses.calls[0].request
202 |         assert req.url == query_user_keys_url
203 |         assert req.method == 'POST'
204 | 
205 |     @responses.activate
206 |     def test_claim_keys(self):
207 |         claim_keys_url = "http://example.com/_matrix/client/r0/keys/claim"
208 |         responses.add(responses.POST, claim_keys_url, body='{}')
209 |         self.cli.api.claim_keys({self.user_id: {self.device_id: "algo"}}, timeout=1000)
210 |         req = responses.calls[0].request
211 |         assert req.url == claim_keys_url
212 |         assert req.method == 'POST'
213 | 
214 |     @responses.activate
215 |     def test_key_changes(self):
216 |         key_changes_url = "http://example.com/_matrix/client/r0/keys/changes"
217 |         responses.add(responses.GET, key_changes_url, body='{}')
218 |         self.cli.api.key_changes('s72594_4483_1934', 's75689_5632_2435')
219 |         req = responses.calls[0].request
220 |         assert req.url.split('?')[0] == key_changes_url
221 |         assert req.method == 'GET'
222 | 
223 | 
224 | class TestSendToDeviceApi:
225 |     cli = client.MatrixClient("http://example.com")
226 |     user_id = "@alice:matrix.org"
227 |     device_id = "JLAFKJWSCS"
228 | 
229 |     @responses.activate
230 |     def test_send_to_device(self):
231 |         txn_id = self.cli.api._make_txn_id()
232 |         send_to_device_url = \
233 |             "http://example.com/_matrix/client/r0/sendToDevice/m.new_device/" + txn_id
234 |         responses.add(responses.PUT, send_to_device_url, body='{}')
235 |         payload = {self.user_id: {self.device_id: {"test": 1}}}
236 |         self.cli.api.send_to_device("m.new_device", payload, txn_id)
237 |         req = responses.calls[0].request
238 |         assert req.url == send_to_device_url
239 |         assert req.method == 'PUT'
240 | 
241 | 
242 | class TestMainApi:
243 |     user_id = "@alice:matrix.org"
244 |     token = "Dp0YKRXwx0iWDhFj7lg3DVjwsWzGcUIgARljgyAip2JD8qd5dSaW" \
245 |         "cxowTKEFetPulfLijAhv8eOmUSScyGcWgZyNMRTBmoJ0RFc0HotPvTBZ" \
246 |         "U98yKRLtat7V43aCpFmK"
247 |     test_path = "/account/whoami"
248 | 
249 |     @responses.activate
250 |     def test_send_token_header(self):
251 |         mapi = api.MatrixHttpApi("http://example.com", token=self.token)
252 |         responses.add(
253 |             responses.GET,
254 |             mapi._base_url+MATRIX_V2_API_PATH+self.test_path,
255 |             body='{"application/json": {"user_id": "%s"}}' % self.user_id
256 |         )
257 |         mapi._send("GET", self.test_path)
258 |         req = responses.calls[0].request
259 |         assert req.method == 'GET'
260 |         assert req.headers['Authorization'] == 'Bearer %s' % self.token
261 | 
262 |     @responses.activate
263 |     def test_send_user_agent_header(self):
264 |         mapi = api.MatrixHttpApi("http://example.com")
265 |         responses.add(
266 |             responses.GET,
267 |             mapi._base_url+MATRIX_V2_API_PATH+self.test_path,
268 |             body='{"application/json": {"user_id": "%s"}}' % self.user_id
269 |         )
270 |         mapi._send("GET", self.test_path)
271 |         req = responses.calls[0].request
272 |         assert req.method == 'GET'
273 |         assert req.headers['User-Agent'] == 'matrix-python-sdk/%s' % lib_version
274 | 
275 |     @responses.activate
276 |     def test_send_token_query(self):
277 |         mapi = api.MatrixHttpApi(
278 |             "http://example.com",
279 |             token=self.token,
280 |             use_authorization_header=False
281 |         )
282 |         responses.add(
283 |             responses.GET,
284 |             mapi._base_url+MATRIX_V2_API_PATH+self.test_path,
285 |             body='{"application/json": {"user_id": "%s"}}' % self.user_id
286 |         )
287 |         mapi._send("GET", self.test_path)
288 |         req = responses.calls[0].request
289 |         assert req.method == 'GET'
290 |         assert self.token in req.url
291 | 
292 |     @responses.activate
293 |     def test_send_user_id(self):
294 |         mapi = api.MatrixHttpApi(
295 |             "http://example.com",
296 |             token=self.token,
297 |             identity=self.user_id
298 |         )
299 |         responses.add(
300 |             responses.GET,
301 |             mapi._base_url+MATRIX_V2_API_PATH+self.test_path,
302 |             body='{"application/json": {"user_id": "%s"}}' % self.user_id
303 |         )
304 |         mapi._send("GET", self.test_path)
305 |         req = responses.calls[0].request
306 |         assert "user_id" in req.url
307 | 
308 |     @responses.activate
309 |     def test_send_unsup_method(self):
310 |         mapi = api.MatrixHttpApi("http://example.com")
311 |         with pytest.raises(MatrixError):
312 |             mapi._send("GOT", self.test_path)
313 | 
314 |     @responses.activate
315 |     def test_send_request_error(self):
316 |         mapi = api.MatrixHttpApi("http://example.com")
317 |         with pytest.raises(MatrixHttpLibError):
318 |             mapi._send("GET", self.test_path)
319 | 
320 | 
321 | class TestMediaApi:
322 |     cli = client.MatrixClient("http://example.com")
323 |     user_id = "@alice:example.com"
324 |     mxcurl = "mxc://example.com/OonjUOmcuVpUnmOWKtzPmAFe"
325 | 
326 |     @responses.activate
327 |     def test_media_download(self):
328 |         media_url = \
329 |             "http://example.com/_matrix/media/r0/download/" + self.mxcurl[6:]
330 |         with open('test/response_examples.py', 'rb') as fil:
331 |             responses.add(
332 |                 responses.GET, media_url,
333 |                 content_type='application/python',
334 |                 body=fil.read(), status=200, stream=True
335 |             )
336 |         resp = self.cli.api.media_download(self.mxcurl, allow_remote=False)
337 |         resp.raw.decode_content = True
338 |         req = responses.calls[0].request
339 |         assert req.url.split('?')[0] == media_url
340 |         assert req.method == 'GET'
341 | 
342 |     def test_media_download_wrong_url(self):
343 |         with pytest.raises(ValueError):
344 |             self.cli.api.media_download(self.mxcurl[6:])
345 | 
346 |     @responses.activate
347 |     def test_get_thumbnail(self):
348 |         media_url = \
349 |             "http://example.com/_matrix/media/r0/thumbnail/" + self.mxcurl[6:]
350 |         with open('test/response_examples.py', 'rb') as fil:
351 |             responses.add(
352 |                 responses.GET, media_url,
353 |                 content_type='application/python',
354 |                 body=fil.read(), status=200, stream=True
355 |             )
356 |         resp = self.cli.api.get_thumbnail(
357 |             self.mxcurl, 28, 28, allow_remote=False
358 |         )
359 |         resp.raw.decode_content = True
360 |         req = responses.calls[0].request
361 |         assert req.url.split('?')[0] == media_url
362 |         assert req.method == 'GET'
363 | 
364 |     def test_get_thumbnail_wrong_url(self):
365 |         with pytest.raises(ValueError):
366 |             self.cli.api.get_thumbnail(self.mxcurl[6:], 28, 28)
367 | 
368 |     def test_get_thumbnail_wrong_method(self):
369 |         with pytest.raises(ValueError):
370 |             self.cli.api.get_thumbnail(self.mxcurl, 28, 28, 'cut')
371 | 
372 |     @responses.activate
373 |     def test_get_url_preview(self):
374 |         media_url = \
375 |             "http://example.com/_matrix/media/r0/preview_url"
376 |         preview_url = deepcopy(response_examples.example_preview_url)
377 |         responses.add(
378 |             responses.GET, media_url,
379 |             body=json.dumps(preview_url)
380 |         )
381 |         self.cli.api.get_url_preview("https://google.com/", 1510610716656)
382 |         req = responses.calls[0].request
383 |         assert req.url.split('?')[0] == media_url
384 |         assert req.method == 'GET'
385 | 
386 | 
387 | class TestRoomApi:
388 |     cli = client.MatrixClient("http://example.com")
389 |     user_id = "@user:matrix.org"
390 |     room_id = "#foo:matrix.org"
391 | 
392 |     @responses.activate
393 |     def test_create_room_visibility_public(self):
394 |         create_room_url = "http://example.com" \
395 |             "/_matrix/client/r0/createRoom"
396 |         responses.add(
397 |             responses.POST,
398 |             create_room_url,
399 |             json='{"room_id": "!sefiuhWgwghwWgh:example.com"}'
400 |         )
401 |         self.cli.api.create_room(
402 |             name="test",
403 |             alias="#test:example.com",
404 |             is_public=True
405 |         )
406 |         req = responses.calls[0].request
407 |         assert req.url == create_room_url
408 |         assert req.method == 'POST'
409 |         j = json.loads(req.body)
410 |         assert j["room_alias_name"] == "#test:example.com"
411 |         assert j["visibility"] == "public"
412 |         assert j["name"] == "test"
413 | 
414 |     @responses.activate
415 |     def test_create_room_visibility_private(self):
416 |         create_room_url = "http://example.com" \
417 |             "/_matrix/client/r0/createRoom"
418 |         responses.add(
419 |             responses.POST,
420 |             create_room_url,
421 |             json='{"room_id": "!sefiuhWgwghwWgh:example.com"}'
422 |         )
423 |         self.cli.api.create_room(
424 |             name="test",
425 |             alias="#test:example.com",
426 |             is_public=False
427 |         )
428 |         req = responses.calls[0].request
429 |         assert req.url == create_room_url
430 |         assert req.method == 'POST'
431 |         j = json.loads(req.body)
432 |         assert j["room_alias_name"] == "#test:example.com"
433 |         assert j["visibility"] == "private"
434 |         assert j["name"] == "test"
435 | 
436 |     @responses.activate
437 |     def test_create_room_federate_true(self):
438 |         create_room_url = "http://example.com" \
439 |             "/_matrix/client/r0/createRoom"
440 |         responses.add(
441 |             responses.POST,
442 |             create_room_url,
443 |             json='{"room_id": "!sefiuhWgwghwWgh:example.com"}'
444 |         )
445 |         self.cli.api.create_room(
446 |             name="test2",
447 |             alias="#test2:example.com",
448 |             federate=True
449 |         )
450 |         req = responses.calls[0].request
451 |         assert req.url == create_room_url
452 |         assert req.method == 'POST'
453 |         j = json.loads(req.body)
454 |         assert j["creation_content"]["m.federate"]
455 | 
456 |     @responses.activate
457 |     def test_create_room_federate_false(self):
458 |         create_room_url = "http://example.com" \
459 |             "/_matrix/client/r0/createRoom"
460 |         responses.add(
461 |             responses.POST,
462 |             create_room_url,
463 |             json='{"room_id": "!sefiuhWgwghwWgh:example.com"}'
464 |         )
465 |         self.cli.api.create_room(
466 |             name="test",
467 |             alias="#test:example.com",
468 |             federate=False
469 |         )
470 |         req = responses.calls[0].request
471 |         assert req.url == create_room_url
472 |         assert req.method == 'POST'
473 |         j = json.loads(req.body)
474 |         assert not j["creation_content"]["m.federate"]
475 | 
476 | 
477 | class TestWhoamiQuery:
478 |     user_id = "@alice:example.com"
479 |     token = "Dp0YKRXwx0iWDhFj7lg3DVjwsWzGcUIgARljgyAip2JD8qd5dSaW" \
480 |             "cxowTKEFetPulfLijAhv8eOmUSScyGcWgZyNMRTBmoJ0RFc0HotPvTBZ" \
481 |             "U98yKRLtat7V43aCpFmK"
482 | 
483 |     @responses.activate
484 |     def test_whoami(self):
485 |         mapi = api.MatrixHttpApi("http://example.com", token=self.token)
486 |         whoami_url = "http://example.com/_matrix/client/r0/account/whoami"
487 |         responses.add(
488 |             responses.GET,
489 |             whoami_url,
490 |             body='{"user_id": "%s"}' % self.user_id
491 |         )
492 |         mapi.whoami()
493 |         req = responses.calls[0].request
494 |         assert req.method == 'GET'
495 |         assert whoami_url in req.url
496 | 
497 |     @responses.activate
498 |     def test_whoami_unauth(self):
499 |         mapi = api.MatrixHttpApi("http://example.com")
500 |         whoami_url = "http://example.com/_matrix/client/r0/account/whoami"
501 |         responses.add(
502 |             responses.GET,
503 |             whoami_url,
504 |             body='{"user_id": "%s"}' % self.user_id
505 |         )
506 |         with pytest.raises(MatrixError):
507 |             mapi.whoami()
508 | 


--------------------------------------------------------------------------------
/test/client_test.py:
--------------------------------------------------------------------------------
  1 | import pytest
  2 | import responses
  3 | import json
  4 | from copy import deepcopy
  5 | from matrix_client.client import MatrixClient, Room, User, CACHE
  6 | from matrix_client.api import MATRIX_V2_API_PATH
  7 | from . import response_examples
  8 | try:
  9 |     from urllib import quote
 10 | except ImportError:
 11 |     from urllib.parse import quote
 12 | 
 13 | HOSTNAME = "http://example.com"
 14 | 
 15 | 
 16 | def test_create_client():
 17 |     MatrixClient("http://example.com")
 18 | 
 19 | 
 20 | @responses.activate
 21 | def test_create_client_with_token():
 22 |     user_id = "@alice:example.com"
 23 |     token = "Dp0YKRXwx0iWDhFj7lg3DVjwsWzGcUIgARljgyAip2JD8qd5dSaW" \
 24 |             "cxowTKEFetPulfLijAhv8eOmUSScyGcWgZyNMRTBmoJ0RFc0HotPvTBZ" \
 25 |             "U98yKRLtat7V43aCpFmK"
 26 |     whoami_url = HOSTNAME+MATRIX_V2_API_PATH+"/account/whoami"
 27 |     responses.add(
 28 |         responses.GET,
 29 |         whoami_url,
 30 |         body='{"user_id": "%s"}' % user_id
 31 |     )
 32 |     sync_response = deepcopy(response_examples.example_sync)
 33 |     response_body = json.dumps(sync_response)
 34 |     sync_url = HOSTNAME + MATRIX_V2_API_PATH + "/sync"
 35 |     responses.add(responses.GET, sync_url, body=response_body)
 36 |     MatrixClient(HOSTNAME, token=token)
 37 |     req = responses.calls[0].request
 38 |     assert req.method == 'GET'
 39 |     assert whoami_url in req.url
 40 | 
 41 | 
 42 | def test_sync_token():
 43 |     client = MatrixClient("http://example.com")
 44 |     assert client.get_sync_token() is None
 45 |     client.set_sync_token("FAKE_TOKEN")
 46 |     assert client.get_sync_token() == "FAKE_TOKEN"
 47 | 
 48 | 
 49 | def test__mkroom():
 50 |     client = MatrixClient("http://example.com")
 51 | 
 52 |     roomId = "!UcYsUzyxTGDxLBEvLz:matrix.org"
 53 |     goodRoom = client._mkroom(roomId)
 54 | 
 55 |     assert isinstance(goodRoom, Room)
 56 |     assert goodRoom.room_id is roomId
 57 | 
 58 |     with pytest.raises(ValueError):
 59 |         client._mkroom("BAD_ROOM:matrix.org")
 60 |         client._mkroom("!BAD_ROOMmatrix.org")
 61 |         client._mkroom("!BAD_ROOM::matrix.org")
 62 | 
 63 | 
 64 | def test_get_rooms():
 65 |     client = MatrixClient("http://example.com")
 66 |     rooms = client.get_rooms()
 67 |     assert isinstance(rooms, dict)
 68 |     assert len(rooms) == 0
 69 | 
 70 |     client = MatrixClient("http://example.com")
 71 | 
 72 |     client._mkroom("!abc:matrix.org")
 73 |     client._mkroom("!def:matrix.org")
 74 |     client._mkroom("!ghi:matrix.org")
 75 | 
 76 |     rooms = client.get_rooms()
 77 |     assert isinstance(rooms, dict)
 78 |     assert len(rooms) == 3
 79 | 
 80 | 
 81 | def test_bad_state_events():
 82 |     client = MatrixClient("http://example.com")
 83 |     room = client._mkroom("!abc:matrix.org")
 84 | 
 85 |     ev = {
 86 |         "tomato": False
 87 |     }
 88 | 
 89 |     room._process_state_event(ev)
 90 | 
 91 | 
 92 | def test_state_event():
 93 |     client = MatrixClient("http://example.com")
 94 |     room = client._mkroom("!abc:matrix.org")
 95 | 
 96 |     room.name = False
 97 |     room.topic = False
 98 |     room.aliases = False
 99 | 
100 |     ev = {
101 |         "type": "m.room.name",
102 |         "content": {},
103 |         "event_id": "$10000000000000AAAAA:matrix.org"
104 |     }
105 | 
106 |     room._process_state_event(ev)
107 |     assert room.name is None
108 | 
109 |     ev["content"]["name"] = "TestName"
110 |     room._process_state_event(ev)
111 |     assert room.name == "TestName"
112 | 
113 |     ev["type"] = "m.room.topic"
114 |     room._process_state_event(ev)
115 |     assert room.topic is None
116 | 
117 |     ev["content"]["topic"] = "TestTopic"
118 |     room._process_state_event(ev)
119 |     assert room.topic == "TestTopic"
120 | 
121 |     ev["type"] = "m.room.aliases"
122 |     room._process_state_event(ev)
123 |     assert room.aliases is None
124 | 
125 |     aliases = ["#foo:matrix.org", "#bar:matrix.org"]
126 |     ev["content"]["aliases"] = aliases
127 |     room._process_state_event(ev)
128 |     assert room.aliases is aliases
129 | 
130 |     # test member join event
131 |     ev["type"] = "m.room.member"
132 |     ev["content"] = {'membership': 'join', 'displayname': 'stereo'}
133 |     ev["state_key"] = "@stereo:xxx.org"
134 |     room._process_state_event(ev)
135 |     assert len(room._members) == 1
136 |     assert room._members["@stereo:xxx.org"]
137 |     # test member leave event
138 |     ev["content"]['membership'] = 'leave'
139 |     room._process_state_event(ev)
140 |     assert len(room._members) == 0
141 | 
142 |     # test join_rules
143 |     room.invite_only = False
144 |     ev["type"] = "m.room.join_rules"
145 |     ev["content"] = {"join_rule": "invite"}
146 |     room._process_state_event(ev)
147 |     assert room.invite_only
148 | 
149 |     # test guest_access
150 |     room.guest_access = False
151 |     ev["type"] = "m.room.guest_access"
152 |     ev["content"] = {"guest_access": "can_join"}
153 |     room._process_state_event(ev)
154 |     assert room.guest_access
155 | 
156 |     # test malformed event (check does not throw exception)
157 |     room.guest_access = False
158 |     ev["type"] = "m.room.guest_access"
159 |     ev["content"] = {}
160 |     room._process_state_event(ev)
161 |     assert not room.guest_access
162 | 
163 |     # test encryption
164 |     room.encrypted = False
165 |     ev["type"] = "m.room.encryption"
166 |     ev["content"] = {"algorithm": "m.megolm.v1.aes-sha2"}
167 |     room._process_state_event(ev)
168 |     assert room.encrypted
169 |     # encrypted flag must not be cleared on configuration change
170 |     ev["content"] = {"algorithm": None}
171 |     room._process_state_event(ev)
172 |     assert room.encrypted
173 | 
174 | 
175 | def test_get_user():
176 |     client = MatrixClient("http://example.com")
177 | 
178 |     assert isinstance(client.get_user("@foobar:matrix.org"), User)
179 | 
180 |     with pytest.raises(ValueError):
181 |         client.get_user("badfoobar:matrix.org")
182 |         client.get_user("@badfoobarmatrix.org")
183 |         client.get_user("@badfoobar:::matrix.org")
184 | 
185 | 
186 | def test_get_download_url():
187 |     client = MatrixClient("http://example.com")
188 |     real_url = "http://example.com/_matrix/media/r0/download/foobar"
189 |     assert client.api.get_download_url("mxc://foobar") == real_url
190 | 
191 |     with pytest.raises(ValueError):
192 |         client.api.get_download_url("http://foobar")
193 | 
194 | 
195 | def test_remove_listener():
196 |     def dummy_listener():
197 |         pass
198 | 
199 |     client = MatrixClient("http://example.com")
200 |     handler = client.add_listener(dummy_listener)
201 | 
202 |     found_listener = False
203 |     for listener in client.listeners:
204 |         if listener["uid"] == handler:
205 |             found_listener = True
206 |             break
207 | 
208 |     assert found_listener, "listener was not added properly"
209 | 
210 |     client.remove_listener(handler)
211 |     found_listener = False
212 |     for listener in client.listeners:
213 |         if listener["uid"] == handler:
214 |             found_listener = True
215 |             break
216 | 
217 |     assert not found_listener, "listener was not removed properly"
218 | 
219 | 
220 | class TestClientRegister:
221 |     cli = MatrixClient(HOSTNAME)
222 | 
223 |     @responses.activate
224 |     def test_register_as_guest(self):
225 |         cli = self.cli
226 | 
227 |         def _sync(self):
228 |             self._sync_called = True
229 |         cli.__dict__[_sync.__name__] = _sync.__get__(cli, cli.__class__)
230 |         register_guest_url = HOSTNAME + MATRIX_V2_API_PATH + "/register"
231 |         response_body = json.dumps({
232 |             'access_token': 'EXAMPLE_ACCESS_TOKEN',
233 |             'device_id': 'guest_device',
234 |             'home_server': 'example.com',
235 |             'user_id': '@455:example.com'
236 |         })
237 |         responses.add(responses.POST, register_guest_url, body=response_body)
238 |         cli.register_as_guest()
239 |         assert cli.token == cli.api.token == 'EXAMPLE_ACCESS_TOKEN'
240 |         assert cli.hs == 'example.com'
241 |         assert cli.user_id == '@455:example.com'
242 |         assert cli._sync_called
243 | 
244 | 
245 | def test_get_rooms_display_name():
246 | 
247 |     def add_members(api, room, num):
248 |         for i in range(num):
249 |             room._add_member('@frho%s:matrix.org' % i, 'ho%s' % i)
250 | 
251 |     client = MatrixClient("http://example.com")
252 |     client.user_id = "@frho0:matrix.org"
253 |     room1 = client._mkroom("!abc:matrix.org")
254 |     add_members(client.api, room1, 1)
255 |     room2 = client._mkroom("!def:matrix.org")
256 |     add_members(client.api, room2, 2)
257 |     room3 = client._mkroom("!ghi:matrix.org")
258 |     add_members(client.api, room3, 3)
259 |     room4 = client._mkroom("!rfi:matrix.org")
260 |     add_members(client.api, room4, 30)
261 | 
262 |     rooms = client.get_rooms()
263 |     assert len(rooms) == 4
264 |     assert room1.display_name == "Empty room"
265 |     assert room2.display_name == "ho1"
266 |     assert room3.display_name == "ho1 and ho2"
267 |     assert room4.display_name == "ho1 and 28 others"
268 | 
269 | 
270 | @responses.activate
271 | def test_presence_listener():
272 |     client = MatrixClient("http://example.com")
273 |     accumulator = []
274 | 
275 |     def dummy_callback(event):
276 |         accumulator.append(event)
277 |     presence_events = [
278 |         {
279 |             "content": {
280 |                 "avatar_url": "mxc://localhost:wefuiwegh8742w",
281 |                 "currently_active": False,
282 |                 "last_active_ago": 2478593,
283 |                 "presence": "online",
284 |                 "user_id": "@example:localhost"
285 |             },
286 |             "event_id": "$WLGTSEFSEF:localhost",
287 |             "type": "m.presence"
288 |         },
289 |         {
290 |             "content": {
291 |                 "avatar_url": "mxc://localhost:weaugwe742w",
292 |                 "currently_active": True,
293 |                 "last_active_ago": 1478593,
294 |                 "presence": "online",
295 |                 "user_id": "@example2:localhost"
296 |             },
297 |             "event_id": "$CIGTXEFREF:localhost",
298 |             "type": "m.presence"
299 |         },
300 |         {
301 |             "content": {
302 |                 "avatar_url": "mxc://localhost:wefudweg13742w",
303 |                 "currently_active": False,
304 |                 "last_active_ago": 24795,
305 |                 "presence": "offline",
306 |                 "user_id": "@example3:localhost"
307 |             },
308 |             "event_id": "$ZEGASEDSEF:localhost",
309 |             "type": "m.presence"
310 |         },
311 |     ]
312 |     sync_response = deepcopy(response_examples.example_sync)
313 |     sync_response["presence"]["events"] = presence_events
314 |     response_body = json.dumps(sync_response)
315 |     sync_url = HOSTNAME + MATRIX_V2_API_PATH + "/sync"
316 | 
317 |     responses.add(responses.GET, sync_url, body=response_body)
318 |     callback_uid = client.add_presence_listener(dummy_callback)
319 |     client._sync()
320 |     assert accumulator == presence_events
321 | 
322 |     responses.add(responses.GET, sync_url, body=response_body)
323 |     client.remove_presence_listener(callback_uid)
324 |     accumulator = []
325 |     client._sync()
326 |     assert accumulator == []
327 | 
328 | 
329 | @responses.activate
330 | def test_changing_user_power_levels():
331 |     client = MatrixClient(HOSTNAME)
332 |     room_id = "!UcYsUzyxTGDxLBEvLz:matrix.org"
333 |     room = client._mkroom(room_id)
334 |     PL_state_path = HOSTNAME + MATRIX_V2_API_PATH + \
335 |         "/rooms/" + quote(room_id) + "/state/m.room.power_levels"
336 | 
337 |     # Code should first get current power_levels and then modify them
338 |     responses.add(responses.GET, PL_state_path,
339 |                   json=response_examples.example_pl_event["content"])
340 |     responses.add(responses.PUT, PL_state_path,
341 |                   json=response_examples.example_event_response)
342 |     # Removes user from user and adds user to to users list
343 |     assert room.modify_user_power_levels(users={"@example:localhost": None,
344 |                                                 "@foobar:example.com": 49})
345 | 
346 |     expected_request = deepcopy(response_examples.example_pl_event["content"])
347 |     del expected_request["users"]["@example:localhost"]
348 |     expected_request["users"]["@foobar:example.com"] = 49
349 | 
350 |     assert json.loads(responses.calls[1].request.body) == expected_request
351 | 
352 | 
353 | @responses.activate
354 | def test_changing_default_power_level():
355 |     client = MatrixClient(HOSTNAME)
356 |     room_id = "!UcYsUzyxTGDxLBEvLz:matrix.org"
357 |     room = client._mkroom(room_id)
358 |     PL_state_path = HOSTNAME + MATRIX_V2_API_PATH + \
359 |         "/rooms/" + quote(room_id) + "/state/m.room.power_levels"
360 | 
361 |     # Code should first get current power_levels and then modify them
362 |     responses.add(responses.GET, PL_state_path,
363 |                   json=response_examples.example_pl_event["content"])
364 |     responses.add(responses.PUT, PL_state_path,
365 |                   json=response_examples.example_event_response)
366 |     assert room.modify_user_power_levels(users_default=23)
367 | 
368 |     expected_request = deepcopy(response_examples.example_pl_event["content"])
369 |     expected_request["users_default"] = 23
370 | 
371 |     assert json.loads(responses.calls[1].request.body) == expected_request
372 | 
373 | 
374 | @responses.activate
375 | def test_changing_event_required_power_levels():
376 |     client = MatrixClient(HOSTNAME)
377 |     room_id = "!UcYsUzyxTGDxLBEvLz:matrix.org"
378 |     room = client._mkroom(room_id)
379 |     PL_state_path = HOSTNAME + MATRIX_V2_API_PATH + \
380 |         "/rooms/" + quote(room_id) + "/state/m.room.power_levels"
381 | 
382 |     # Code should first get current power_levels and then modify them
383 |     responses.add(responses.GET, PL_state_path,
384 |                   json=response_examples.example_pl_event["content"])
385 |     responses.add(responses.PUT, PL_state_path,
386 |                   json=response_examples.example_event_response)
387 |     # Remove event from events and adds new controlled event
388 |     assert room.modify_required_power_levels(events={"m.room.name": None,
389 |                                                      "example.event": 51})
390 | 
391 |     expected_request = deepcopy(response_examples.example_pl_event["content"])
392 |     del expected_request["events"]["m.room.name"]
393 |     expected_request["events"]["example.event"] = 51
394 | 
395 |     assert json.loads(responses.calls[1].request.body) == expected_request
396 | 
397 | 
398 | @responses.activate
399 | def test_changing_other_required_power_levels():
400 |     client = MatrixClient(HOSTNAME)
401 |     room_id = "!UcYsUzyxTGDxLBEvLz:matrix.org"
402 |     room = client._mkroom(room_id)
403 |     PL_state_path = HOSTNAME + MATRIX_V2_API_PATH + \
404 |         "/rooms/" + quote(room_id) + "/state/m.room.power_levels"
405 | 
406 |     # Code should first get current power_levels and then modify them
407 |     responses.add(responses.GET, PL_state_path,
408 |                   json=response_examples.example_pl_event["content"])
409 |     responses.add(responses.PUT, PL_state_path,
410 |                   json=response_examples.example_event_response)
411 |     # Remove event from events and adds new controlled event
412 |     assert room.modify_required_power_levels(kick=53, redact=2,
413 |                                              state_default=None)
414 | 
415 |     expected_request = deepcopy(response_examples.example_pl_event["content"])
416 |     expected_request["kick"] = 53
417 |     expected_request["redact"] = 2
418 |     del expected_request["state_default"]
419 | 
420 |     assert json.loads(responses.calls[1].request.body) == expected_request
421 | 
422 | 
423 | @responses.activate
424 | def test_cache():
425 |     m_none = MatrixClient("http://example.com", cache_level=CACHE.NONE)
426 |     m_some = MatrixClient("http://example.com", cache_level=CACHE.SOME)
427 |     m_all = MatrixClient("http://example.com", cache_level=CACHE.ALL)
428 |     sync_url = HOSTNAME + MATRIX_V2_API_PATH + "/sync"
429 |     room_id = "!726s6s6q:example.com"
430 |     room_name = "The FooBar"
431 |     sync_response = deepcopy(response_examples.example_sync)
432 | 
433 |     with pytest.raises(ValueError):
434 |         MatrixClient("http://example.com", cache_level=1)
435 |         MatrixClient("http://example.com", cache_level=5)
436 |         MatrixClient("http://example.com", cache_level=0.5)
437 |         MatrixClient("http://example.com", cache_level=-5)
438 |         MatrixClient("http://example.com", cache_level="foo")
439 |         MatrixClient("http://example.com", cache_level=0.0)
440 | 
441 |     sync_response["rooms"]["join"][room_id]["state"]["events"].append(
442 |         {
443 |             "sender": "@alice:example.com",
444 |             "type": "m.room.name",
445 |             "state_key": "",
446 |             "content": {"name": room_name},
447 |         }
448 |     )
449 | 
450 |     responses.add(responses.GET, sync_url, json.dumps(sync_response))
451 |     m_none._sync()
452 |     responses.add(responses.GET, sync_url, json.dumps(sync_response))
453 |     m_some._sync()
454 |     responses.add(responses.GET, sync_url, json.dumps(sync_response))
455 |     m_all._sync()
456 | 
457 |     assert m_none.rooms[room_id].name is None
458 |     assert m_some.rooms[room_id].name == room_name
459 |     assert m_all.rooms[room_id].name == room_name
460 | 
461 |     assert m_none.rooms[room_id]._members == m_some.rooms[room_id]._members == {}
462 |     assert len(m_all.rooms[room_id]._members) == 2
463 |     assert m_all.rooms[room_id]._members["@alice:example.com"]
464 | 
465 | 
466 | @responses.activate
467 | def test_room_join_rules():
468 |     client = MatrixClient(HOSTNAME)
469 |     room_id = "!UcYsUzyxTGDxLBEvLz:matrix.org"
470 |     room = client._mkroom(room_id)
471 |     assert room.invite_only is None
472 |     join_rules_state_path = HOSTNAME + MATRIX_V2_API_PATH + \
473 |         "/rooms/" + quote(room_id) + "/state/m.room.join_rules"
474 | 
475 |     responses.add(responses.PUT, join_rules_state_path,
476 |                   json=response_examples.example_event_response)
477 | 
478 |     assert room.set_invite_only(True)
479 |     assert room.invite_only
480 | 
481 | 
482 | @responses.activate
483 | def test_room_guest_access():
484 |     client = MatrixClient(HOSTNAME)
485 |     room_id = "!UcYsUzyxTGDxLBEvLz:matrix.org"
486 |     room = client._mkroom(room_id)
487 |     assert room.guest_access is None
488 |     guest_access_state_path = HOSTNAME + MATRIX_V2_API_PATH + \
489 |         "/rooms/" + quote(room_id) + "/state/m.room.guest_access"
490 | 
491 |     responses.add(responses.PUT, guest_access_state_path,
492 |                   json=response_examples.example_event_response)
493 | 
494 |     assert room.set_guest_access(True)
495 |     assert room.guest_access
496 | 
497 | 
498 | @responses.activate
499 | def test_enable_encryption():
500 |     pytest.importorskip('olm')
501 |     client = MatrixClient(HOSTNAME, encryption=True)
502 | 
503 |     login_path = HOSTNAME + MATRIX_V2_API_PATH + "/login"
504 |     responses.add(responses.POST, login_path,
505 |                   json=response_examples.example_success_login_response)
506 | 
507 |     upload_path = HOSTNAME + MATRIX_V2_API_PATH + '/keys/upload'
508 |     responses.add(responses.POST, upload_path, body='{"one_time_key_counts": {}}')
509 | 
510 |     client.login("@example:localhost", "password", sync=False)
511 | 
512 |     assert client.olm_device
513 | 
514 | 
515 | @responses.activate
516 | def test_enable_encryption_in_room():
517 |     pytest.importorskip('olm')
518 |     client = MatrixClient(HOSTNAME)
519 |     room_id = "!UcYsUzyxTGDxLBEvLz:matrix.org"
520 |     room = client._mkroom(room_id)
521 |     assert not room.encrypted
522 |     encryption_state_path = HOSTNAME + MATRIX_V2_API_PATH + \
523 |         "/rooms/" + quote(room_id) + "/state/m.room.encryption"
524 | 
525 |     responses.add(responses.PUT, encryption_state_path,
526 |                   json=response_examples.example_event_response)
527 | 
528 |     assert room.enable_encryption()
529 |     assert room.encrypted
530 | 
531 | 
532 | @responses.activate
533 | def test_detect_encryption_state():
534 |     pytest.importorskip('olm')
535 |     client = MatrixClient(HOSTNAME, encryption=True)
536 |     room_id = "!UcYsUzyxTGDxLBEvLz:matrix.org"
537 | 
538 |     encryption_state_path = HOSTNAME + MATRIX_V2_API_PATH + \
539 |         "/rooms/" + quote(room_id) + "/state/m.room.encryption"
540 |     responses.add(responses.GET, encryption_state_path,
541 |                   json={"algorithm": "m.megolm.v1.aes-sha2"})
542 |     responses.add(responses.GET, encryption_state_path,
543 |                   json={}, status=404)
544 | 
545 |     room = client._mkroom(room_id)
546 |     assert room.encrypted
547 | 
548 |     room = client._mkroom(room_id)
549 |     assert not room.encrypted
550 | 
551 | 
552 | @responses.activate
553 | def test_one_time_keys_sync():
554 |     pytest.importorskip('olm')
555 |     client = MatrixClient(HOSTNAME, encryption=True)
556 |     sync_url = HOSTNAME + MATRIX_V2_API_PATH + "/sync"
557 |     sync_response = deepcopy(response_examples.example_sync)
558 |     payload = {'dummy': 1}
559 |     sync_response["device_one_time_keys_count"] = payload
560 |     sync_response['rooms']['join'] = {}
561 | 
562 |     class DummyDevice:
563 | 
564 |         def update_one_time_key_counts(self, payload):
565 |             self.payload = payload
566 | 
567 |     device = DummyDevice()
568 |     client.olm_device = device
569 | 
570 |     responses.add(responses.GET, sync_url, json=sync_response)
571 | 
572 |     client._sync()
573 |     assert device.payload == payload
574 | 


--------------------------------------------------------------------------------
/test/crypto/olm_device_test.py:
--------------------------------------------------------------------------------
  1 | import pytest
  2 | pytest.importorskip("olm")  # noqa
  3 | 
  4 | import json
  5 | from copy import deepcopy
  6 | 
  7 | import responses
  8 | 
  9 | from matrix_client.api import MATRIX_V2_API_PATH
 10 | from matrix_client.client import MatrixClient
 11 | from matrix_client.crypto.olm_device import OlmDevice
 12 | from test.response_examples import example_key_upload_response
 13 | 
 14 | HOSTNAME = 'http://example.com'
 15 | 
 16 | 
 17 | class TestOlmDevice:
 18 |     cli = MatrixClient(HOSTNAME)
 19 |     user_id = '@user:matrix.org'
 20 |     device_id = 'QBUAZIFURK'
 21 |     device = OlmDevice(cli.api, user_id, device_id)
 22 |     signing_key = device.olm_account.identity_keys['ed25519']
 23 | 
 24 |     def test_sign_json(self):
 25 |         example_payload = {
 26 |             "name": "example.org",
 27 |             "unsigned": {
 28 |                 "age_ts": 922834800000
 29 |             }
 30 |         }
 31 |         saved_payload = deepcopy(example_payload)
 32 | 
 33 |         signed_payload = self.device.sign_json(example_payload)
 34 |         signature = signed_payload.pop('signatures')
 35 |         # We should not have modified the payload besides the signatures key
 36 |         assert example_payload == saved_payload
 37 |         key_id = 'ed25519:' + self.device_id
 38 |         assert signature[self.user_id][key_id]
 39 | 
 40 |     def test_verify_json(self):
 41 |         example_payload = {
 42 |             "test": "test",
 43 |             "unsigned": {
 44 |                 "age_ts": 922834800000
 45 |             },
 46 |             "signatures": {
 47 |                 "@user:matrix.org": {
 48 |                     "ed25519:QBUAZIFURK": ("WI7TgwqTp4YVn1dFWmDu7xrJvEikEzAbmoqyM5JY5t0P"
 49 |                                            "6fVaiMFAirmwb13GzIyYDLR+nQfoksNBcrp7xSaMCA")
 50 |                 }
 51 |             }
 52 |         }
 53 |         saved_payload = deepcopy(example_payload)
 54 |         signing_key = "WQF5z9b4DV1DANI5HUMJfhTIDvJs1jkoGTLY6AQdjF0"
 55 | 
 56 |         assert self.device.verify_json(example_payload, signing_key, self.user_id,
 57 |                                        self.device_id)
 58 | 
 59 |         # We should not have modified the payload
 60 |         assert example_payload == saved_payload
 61 | 
 62 |         # Try to verify an object that has been tampered with
 63 |         example_payload['test'] = 'test1'
 64 |         assert not self.device.verify_json(example_payload, signing_key, self.user_id,
 65 |                                            self.device_id)
 66 | 
 67 |         # Try to verify invalid payloads
 68 |         example_payload['signatures'].pop(self.user_id)
 69 |         assert not self.device.verify_json(example_payload, signing_key, self.user_id,
 70 |                                            self.device_id)
 71 |         example_payload.pop('signatures')
 72 |         assert not self.device.verify_json(example_payload, signing_key, self.user_id,
 73 |                                            self.device_id)
 74 | 
 75 |     def test_sign_verify(self):
 76 |         example_payload = {
 77 |             "name": "example.org",
 78 |         }
 79 | 
 80 |         signed_payload = self.device.sign_json(example_payload)
 81 |         assert self.device.verify_json(signed_payload, self.signing_key, self.user_id,
 82 |                                        self.device_id)
 83 | 
 84 |     @responses.activate
 85 |     def test_upload_identity_keys(self):
 86 |         upload_url = HOSTNAME + MATRIX_V2_API_PATH + '/keys/upload'
 87 |         self.device.one_time_keys_manager.server_counts = {}
 88 |         resp = deepcopy(example_key_upload_response)
 89 | 
 90 |         responses.add(responses.POST, upload_url, json=resp)
 91 | 
 92 |         assert self.device.upload_identity_keys() is None
 93 |         assert self.device.one_time_keys_manager.server_counts == \
 94 |             resp['one_time_key_counts']
 95 | 
 96 |         req_device_keys = json.loads(responses.calls[0].request.body)['device_keys']
 97 |         assert req_device_keys['user_id'] == self.user_id
 98 |         assert req_device_keys['device_id'] == self.device_id
 99 |         assert req_device_keys['algorithms'] == self.device._algorithms
100 |         assert 'keys' in req_device_keys
101 |         assert 'signatures' in req_device_keys
102 |         assert self.device.verify_json(req_device_keys, self.signing_key, self.user_id,
103 |                                        self.device_id)
104 | 
105 |     @pytest.mark.parametrize('proportion', [-1, 2])
106 |     def test_upload_identity_keys_invalid(self, proportion):
107 |         with pytest.raises(ValueError):
108 |             OlmDevice(self.cli.api,
109 |                       self.user_id,
110 |                       self.device_id,
111 |                       signed_keys_proportion=proportion)
112 | 
113 |     @responses.activate
114 |     @pytest.mark.parametrize('proportion', [0, 1, 0.5, 0.33])
115 |     def test_upload_one_time_keys(self, proportion):
116 |         upload_url = HOSTNAME + MATRIX_V2_API_PATH + '/keys/upload'
117 |         resp = deepcopy(example_key_upload_response)
118 |         counts = resp['one_time_key_counts']
119 |         counts['curve25519'] = counts['signed_curve25519'] = 10
120 |         responses.add(responses.POST, upload_url, json=resp)
121 | 
122 |         device = OlmDevice(
123 |             self.cli.api, self.user_id, self.device_id, signed_keys_proportion=proportion)
124 |         assert not device.one_time_keys_manager.server_counts
125 | 
126 |         max_keys = device.olm_account.max_one_time_keys // 2
127 |         signed_keys_to_upload = \
128 |             max(round(max_keys * proportion) - counts['signed_curve25519'], 0)
129 |         unsigned_keys_to_upload = \
130 |             max(round(max_keys * (1 - proportion)) - counts['curve25519'], 0)
131 |         expected_return = {}
132 |         if signed_keys_to_upload:
133 |             expected_return['signed_curve25519'] = signed_keys_to_upload
134 |         if unsigned_keys_to_upload:
135 |             expected_return['curve25519'] = unsigned_keys_to_upload
136 | 
137 |         assert device.upload_one_time_keys() == expected_return
138 |         assert len(responses.calls) == 2
139 |         assert device.one_time_keys_manager.server_counts == resp['one_time_key_counts']
140 | 
141 |         req_otk = json.loads(responses.calls[1].request.body)['one_time_keys']
142 |         assert len(req_otk) == unsigned_keys_to_upload + signed_keys_to_upload
143 |         assert len([key for key in req_otk if not key.startswith('signed')]) == \
144 |             unsigned_keys_to_upload
145 |         assert len([key for key in req_otk if key.startswith('signed')]) == \
146 |             signed_keys_to_upload
147 |         for k in req_otk:
148 |             if k == 'signed_curve25519':
149 |                 device.verify_json(req_otk[k], device.signing_key, device.user_id,
150 |                                    device.device_id)
151 | 
152 |     @responses.activate
153 |     def test_upload_one_time_keys_enough(self):
154 |         upload_url = HOSTNAME + MATRIX_V2_API_PATH + '/keys/upload'
155 |         self.device.one_time_keys_manager.server_counts = {}
156 |         limit = self.device.olm_account.max_one_time_keys // 2
157 |         resp = {'one_time_key_counts': {'signed_curve25519': limit}}
158 |         responses.add(responses.POST, upload_url, json=resp)
159 | 
160 |         assert not self.device.upload_one_time_keys()
161 | 
162 |     @responses.activate
163 |     def test_upload_one_time_keys_force_update(self):
164 |         upload_url = HOSTNAME + MATRIX_V2_API_PATH + '/keys/upload'
165 |         self.device.one_time_keys_manager.server_counts = {'curve25519': 10}
166 |         resp = deepcopy(example_key_upload_response)
167 |         responses.add(responses.POST, upload_url, json=resp)
168 | 
169 |         self.device.upload_one_time_keys()
170 |         assert len(responses.calls) == 1
171 | 
172 |         self.device.upload_one_time_keys(force_update=True)
173 |         assert len(responses.calls) == 3
174 | 
175 |     @responses.activate
176 |     @pytest.mark.parametrize('count,should_upload', [(0, True), (25, False), (4, True)])
177 |     def test_update_one_time_key_counts(self, count, should_upload):
178 |         upload_url = HOSTNAME + MATRIX_V2_API_PATH + '/keys/upload'
179 |         responses.add(responses.POST, upload_url, json={'one_time_key_counts': {}})
180 |         self.device.one_time_keys_manager.target_counts['signed_curve25519'] = 50
181 |         self.device.one_time_keys_manager.server_counts.clear()
182 | 
183 |         count_dict = {}
184 |         if count:
185 |             count_dict['signed_curve25519'] = count
186 | 
187 |         self.device.update_one_time_key_counts(count_dict)
188 | 
189 |         if should_upload:
190 |             if count:
191 |                 req_otk = json.loads(responses.calls[0].request.body)['one_time_keys']
192 |                 assert len(responses.calls) == 1
193 |             else:
194 |                 req_otk = json.loads(responses.calls[1].request.body)['one_time_keys']
195 |                 assert len(responses.calls) == 2
196 |             assert len(req_otk) == 50 - count
197 |         else:
198 |             assert not len(responses.calls)
199 | 
200 |     @pytest.mark.parametrize('threshold', [-1, 2])
201 |     def test_invalid_keys_threshold(self, threshold):
202 |         with pytest.raises(ValueError):
203 |             OlmDevice(self.cli.api,
204 |                       self.user_id,
205 |                       self.device_id,
206 |                       keys_threshold=threshold)
207 | 


--------------------------------------------------------------------------------
/test/response_examples.py:
--------------------------------------------------------------------------------
  1 | example_sync = {
  2 |     "next_batch": "s72595_4483_1934",
  3 |     "presence": {
  4 |         "events": [
  5 |             {
  6 |                 "sender": "@alice:example.com",
  7 |                 "type": "m.presence",
  8 |                 "content": {
  9 |                     "presence": "online"
 10 |                 }
 11 |             }
 12 |         ]
 13 |     },
 14 |     "account_data": {
 15 |         "events": [
 16 |             {
 17 |                 "type": "org.example.custom.config",
 18 |                 "content": {
 19 |                     "custom_config_key": "custom_config_value"
 20 |                 }
 21 |             }
 22 |         ]
 23 |     },
 24 |     "rooms": {
 25 |         "join": {
 26 |             "!726s6s6q:example.com": {
 27 |                 "state": {
 28 |                     "events": [
 29 |                         {
 30 |                             "sender": "@alice:example.com",
 31 |                             "type": "m.room.member",
 32 |                             "state_key": "@alice:example.com",
 33 |                             "content": {
 34 |                                 "membership": "join"
 35 |                             },
 36 |                             "origin_server_ts": 1417731086795,
 37 |                             "event_id": "$66697273743031:example.com"
 38 |                         }
 39 |                     ]
 40 |                 },
 41 |                 "timeline": {
 42 |                     "events": [
 43 |                         {
 44 |                             "sender": "@bob:example.com",
 45 |                             "type": "m.room.member",
 46 |                             "state_key": "@bob:example.com",
 47 |                             "content": {
 48 |                                 "membership": "join"
 49 |                             },
 50 |                             "prev_content": {
 51 |                                 "membership": "invite"
 52 |                             },
 53 |                             "origin_server_ts": 1417731086795,
 54 |                             "event_id": "$7365636s6r6432:example.com"
 55 |                         },
 56 |                         {
 57 |                             "sender": "@alice:example.com",
 58 |                             "type": "m.room.message",
 59 |                             "age": 124524,
 60 |                             "txn_id": "1234",
 61 |                             "content": {
 62 |                                 "body": "I am a fish",
 63 |                                 "msgtype": "m.text"
 64 |                             },
 65 |                             "origin_server_ts": 1417731086797,
 66 |                             "event_id": "$74686972643033:example.com"
 67 |                         }
 68 |                     ],
 69 |                     "limited": True,
 70 |                     "prev_batch": "t34-23535_0_0"
 71 |                 },
 72 |                 "ephemeral": {
 73 |                     "events": [
 74 |                         {
 75 |                             "type": "m.typing",
 76 |                             "content": {
 77 |                                 "user_ids": [
 78 |                                     "@alice:example.com"
 79 |                                 ]
 80 |                             }
 81 |                         }
 82 |                     ]
 83 |                 },
 84 |                 "account_data": {
 85 |                     "events": [
 86 |                         {
 87 |                             "type": "m.tag",
 88 |                             "content": {
 89 |                                 "tags": {
 90 |                                     "work": {
 91 |                                         "order": 1
 92 |                                     }
 93 |                                 }
 94 |                             }
 95 |                         },
 96 |                         {
 97 |                             "type": "org.example.custom.room.config",
 98 |                             "content": {
 99 |                                 "custom_config_key": "custom_config_value"
100 |                             }
101 |                         }
102 |                     ]
103 |                 }
104 |             }
105 |         },
106 |         "invite": {
107 |             "!696r7674:example.com": {
108 |                 "invite_state": {
109 |                     "events": [
110 |                         {
111 |                             "sender": "@alice:example.com",
112 |                             "type": "m.room.name",
113 |                             "state_key": "",
114 |                             "content": {
115 |                                 "name": "My Room Name"
116 |                             }
117 |                         },
118 |                         {
119 |                             "sender": "@alice:example.com",
120 |                             "type": "m.room.member",
121 |                             "state_key": "@bob:example.com",
122 |                             "content": {
123 |                                 "membership": "invite"
124 |                             }
125 |                         }
126 |                     ]
127 |                 }
128 |             }
129 |         },
130 |         "leave": {}
131 |     }
132 | }
133 | 
134 | example_pl_event = {
135 |     "age": 242352,
136 |     "content": {
137 |         "ban": 50,
138 |         "events": {
139 |             "m.room.name": 100,
140 |             "m.room.power_levels": 100
141 |         },
142 |         "events_default": 0,
143 |         "invite": 50,
144 |         "kick": 50,
145 |         "redact": 50,
146 |         "state_default": 50,
147 |         "users": {
148 |             "@example:localhost": 100
149 |         },
150 |         "users_default": 0
151 |     },
152 |     "event_id": "$WLGTSEFSEF:localhost",
153 |     "origin_server_ts": 1431961217939,
154 |     "room_id": "!Cuyf34gef24t:localhost",
155 |     "sender": "@example:localhost",
156 |     "state_key": "",
157 |     "type": "m.room.power_levels"
158 | }
159 | 
160 | example_event_response = {
161 |     "event_id": "YUwRidLecu"
162 | }
163 | 
164 | example_key_upload_response = {
165 |     "one_time_key_counts": {
166 |         "curve25519": 10,
167 |         "signed_curve25519": 20
168 |     }
169 | }
170 | 
171 | example_success_login_response = {
172 |     "user_id": "@example:localhost",
173 |     "access_token": "abc123",
174 |     "home_server": "matrix.org",
175 |     "device_id": "GHTYAJCE"
176 | }
177 | 
178 | example_preview_url = {
179 |     "matrix:image:size": 102400,
180 |     "og:description": "This is a really cool blog post from matrix.org",
181 |     "og:image": "mxc://example.com/ascERGshawAWawugaAcauga",
182 |     "og:image:height": 48,
183 |     "og:image:type": "image/png",
184 |     "og:image:width": 48,
185 |     "og:title": "Matrix Blog Post"
186 | }
187 | 


--------------------------------------------------------------------------------
/test/user_test.py:
--------------------------------------------------------------------------------
 1 | import pytest
 2 | import responses
 3 | 
 4 | from matrix_client.api import MATRIX_V2_API_PATH
 5 | from matrix_client.client import MatrixClient
 6 | from matrix_client.user import User
 7 | 
 8 | HOSTNAME = "http://localhost"
 9 | 
10 | 
11 | class TestUser:
12 |     cli = MatrixClient(HOSTNAME)
13 |     user_id = "@test:localhost"
14 |     room_id = "!test:localhost"
15 | 
16 |     @pytest.fixture()
17 |     def user(self):
18 |         return User(self.cli.api, self.user_id)
19 | 
20 |     @pytest.fixture()
21 |     def room(self):
22 |         return self.cli._mkroom(self.room_id)
23 | 
24 |     @responses.activate
25 |     def test_get_display_name(self, user, room):
26 |         displayname_url = HOSTNAME + MATRIX_V2_API_PATH + \
27 |             "/profile/{}/displayname".format(user.user_id)
28 |         displayname = 'test'
29 |         room_displayname = 'room_test'
30 | 
31 |         # No displayname
32 |         assert user.get_display_name(room) == user.user_id
33 |         responses.add(responses.GET, displayname_url, json={})
34 |         assert user.get_display_name() == user.user_id
35 |         assert len(responses.calls) == 1
36 | 
37 |         # Get global displayname
38 |         responses.replace(responses.GET, displayname_url,
39 |                           json={"displayname": displayname})
40 |         assert user.get_display_name() == displayname
41 |         assert len(responses.calls) == 2
42 | 
43 |         # Global displayname already present
44 |         assert user.get_display_name() == displayname
45 |         # No new request
46 |         assert len(responses.calls) == 2
47 | 
48 |         # Per-room displayname
49 |         room.members_displaynames[user.user_id] = room_displayname
50 |         assert user.get_display_name(room) == room_displayname
51 |         # No new request
52 |         assert len(responses.calls) == 2
53 | 


--------------------------------------------------------------------------------