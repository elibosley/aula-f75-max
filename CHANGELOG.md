# Changelog

## [0.3.0](https://github.com/elibosley/aula-f75-max/compare/v0.2.0...v0.3.0) (2026-11-19)


### Features

* recover battery logging and share S75 diagnostics ([#7](https://github.com/elibosley/aula-f75-max/issues/7)) ([d089780](https://github.com/elibosley/aula-f75-max/commit/d089780e559114d1e2cdd146b452be35d005c189))

## [0.2.0](https://github.com/elibosley/aula-f75-max/compare/v0.1.0...v0.2.0) (2026-11-19)


### Features

* add a visiting cat and reduce display and Bluetooth settings work ([360aa65](https://github.com/elibosley/aula-f75-max/commit/360aa658820999e549dff5a21aca635b71144cc6))
* add battery calibration and fractional estimates ([93cfa48](https://github.com/elibosley/aula-f75-max/commit/93cfa48804c374c4164c8219870bd45903883193))
* add S75 Pro firmware and automated desktop releases ([bc25b1b](https://github.com/elibosley/aula-f75-max/commit/bc25b1be94aa824deda8de1527aa09435b97b969))
* add S75 Pro simulator and USB installation workflow ([aac2a89](https://github.com/elibosley/aula-f75-max/commit/aac2a89668382978d80f9748aff20c6d3986ff68))
* **companions:** add four selectable animated desk pets ([4bf3a59](https://github.com/elibosley/aula-f75-max/commit/4bf3a59731860b4a2e94156c102346ee55532371))
* **diagnostics:** add bounded read-only asset flash probe ([5e73add](https://github.com/elibosley/aula-f75-max/commit/5e73addabd9933b123e774cbc614a6f321d7f25c))
* **firmware:** publish F75 Studio with colors and Bluetooth switching ([f5e13bf](https://github.com/elibosley/aula-f75-max/commit/f5e13bf8c42ce752f619e1ac5faaad42eddb5e84))
* **release:** publish verified desktop and firmware assets with Release Please ([aa3a0e4](https://github.com/elibosley/aula-f75-max/commit/aa3a0e4251a594f61034fae31a8853d557ee6c0f))
* **s75pro:** add linked firmware port and model-aware controls ([5845c2e](https://github.com/elibosley/aula-f75-max/commit/5845c2ea90591d17a7d2596d52f9bd9500df6eea))
* show menu position beside the wheel selection ([509c658](https://github.com/elibosley/aula-f75-max/commit/509c658cb02a4afc655d50b645b0be7c3eb68806))
* **studio:** add desktop editor and USB display status ([d895e0e](https://github.com/elibosley/aula-f75-max/commit/d895e0e611c374845bf34573cf59c8ab98088030))
* **ui:** expand lighting and accent palettes with custom hex colors ([8cb9de8](https://github.com/elibosley/aula-f75-max/commit/8cb9de88a5a06fd7e541541fed83d2eba28ddd3a))


### Bug Fixes

* allow delayed radio sleep acknowledgments ([9c8f92a](https://github.com/elibosley/aula-f75-max/commit/9c8f92a212cc2e8b427565b618eb68c617281c38))
* **build:** extract pinned QEMU sources safely on clean hosts ([14daec7](https://github.com/elibosley/aula-f75-max/commit/14daec7a5896aeb3d4cf721a61c895031c1a6375))
* **ci:** decouple ARM clock checks from native preview ([b2cce87](https://github.com/elibosley/aula-f75-max/commit/b2cce876b838352e213a6504eb55a4b4d1014bd5))
* **ci:** run offline settings checks without loading HID ([1e4cd8b](https://github.com/elibosley/aula-f75-max/commit/1e4cd8bd2b142be2ae188475ee4776645f084347))
* **companions:** speed decoding and separate wake deadlines ([2f30d05](https://github.com/elibosley/aula-f75-max/commit/2f30d05a99a012952e3ddf6bd725a75fae88615e))
* **companions:** yield sprite decoding between display tiles ([983ce1a](https://github.com/elibosley/aula-f75-max/commit/983ce1a35aee80abc6b944ce4b9c53da4372cdbe))
* drive the dedicated Caps Lock indicator from active host state ([d65e92b](https://github.com/elibosley/aula-f75-max/commit/d65e92bbe0e668659ab7236e5ea5bc865480a634))
* persist the last successful Bluetooth slot independently of settings ([976cffc](https://github.com/elibosley/aula-f75-max/commit/976cffcccbb139519545cc0788c9cb8f4547f4c4))
* preserve battery recording through Bluetooth sleep gaps ([8b26e91](https://github.com/elibosley/aula-f75-max/commit/8b26e91c23f7c88e1b911d7b25ab9c3b3d16a583))
* **radio:** preserve link state across UART report timeouts ([c003d8d](https://github.com/elibosley/aula-f75-max/commit/c003d8d2d089480814a42f843ff772ce1ff64c57))
* **release:** bind firmware verification to its source commit ([09e6cd8](https://github.com/elibosley/aula-f75-max/commit/09e6cd8fb567f2d0ce1ca927a600a324709d43dc))
* **release:** sanitize source metadata and include build inputs ([a492a69](https://github.com/elibosley/aula-f75-max/commit/a492a69cb4dfb27357e7903c3670ee3d3823dc46))
* remove duplicate release manifest object ([#2](https://github.com/elibosley/aula-f75-max/issues/2)) ([00bc398](https://github.com/elibosley/aula-f75-max/commit/00bc39835f563ed4fa7d9d3f8cf2f5477eea4816))
* **s75pro:** leave unqualified F75 auxiliary outputs untouched ([16a8157](https://github.com/elibosley/aula-f75-max/commit/16a815795e2482da9bb97919aca3fa49d11d0d07))
* **studio:** read bundled assets as UTF-8 on Windows ([c524e37](https://github.com/elibosley/aula-f75-max/commit/c524e37b5c0bdbe1cb164ea91eb948dfe50b7c52))
* use package slug for release branches ([#3](https://github.com/elibosley/aula-f75-max/issues/3)) ([ab657d5](https://github.com/elibosley/aula-f75-max/commit/ab657d5efdd45eb2eecae2e190c14f615edbef10))
