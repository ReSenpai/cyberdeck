#!/usr/bin/env python3
"""adduser — завести пользователя на удалённом сервере по SSH (один вызов).

Подключается системным ``ssh`` (никаких зависимостей: работают ~/.ssh/config,
ключи, ssh-agent, known_hosts) и прогоняет на сервере сгенерированный
идемпотентный bash-скрипт. Скрипт уходит по зашифрованному stdin в ``bash -s`` —
не через argv, поэтому секреты не светятся в ``ps`` на сервере.

Умеет:
  * обычный пользователь или админ (--admin: в группу sudo/wheel);
  * sudo без пароля (--nopasswd-sudo, проверяется через visudo);
  * пароль: --random-password (сгенерит и покажет), --ask-password (скрытый
    ввод), --password (в аргументе); без флага — вход только по ключу;
  * SSH-ключ: --ssh-key '<строка>' или --ssh-key-file pub.key.

Цели берутся из аргументов (``root@host``) или со stdin (конверт cyberdeck.v1 —
можно пайпить живые хосты из ipscan). Результат — тот же конверт: каждый сервер
это host с полем ``user`` (что сделали) и журналом ``actions``.

    adduser.py root@1.2.3.4 -u deploy --ssh-key-file id.pub
    adduser.py 10.0.0.5 -u ops --admin --random-password
    ipscan.py hosts.txt --alive-only --json | adduser.py -u ci --nopasswd-sudo --ssh-key-file ci.pub --json

Логи/прогресс — в stderr, JSON (--json) или отчёт — в stdout. Перед боем удобно
прогнать с --dry-run: покажет удалённый скрипт (пароль скрыт), никуда не подключаясь.
"""

from __future__ import annotations

# ==== cyberdeck inlined by build.py — НЕ РЕДАКТИРОВАТЬ (правь cyberdeck/ и пересобери) ====
import sys as _sys, types as _types, base64 as _b64
def _cd(_n, _src):
    _m = _types.ModuleType(_n); _m.__package__ = _n.rpartition('.')[0]
    _sys.modules[_n] = _m
    exec(compile(_b64.b64decode(_src).decode('utf-8'), '<' + _n + '>', 'exec'), _m.__dict__)
    setattr(_sys.modules[_m.__package__], _n.rpartition('.')[2], _m)
    return _m
_cd_pkg = _types.ModuleType('cyberdeck'); _cd_pkg.__path__ = []; _cd_pkg.__package__ = 'cyberdeck'
_sys.modules['cyberdeck'] = _cd_pkg
_cd('cyberdeck.envelope', 'IiIi0JXQtNC40L3Ri9C5IEpTT04t0LrQvtC90YLRgNCw0LrRgiDQutC40LHQtdGA0LTQtdC60LggKHNjaGVtYTogY3liZXJkZWNrLnYxKS4KCtCf0YDQsNCy0LjQu9CwINC/0LDQudC/0L7QsjoKICAqINC80LDRiNC40L3QvdGL0LkgSlNPTiAgLT4gc3Rkb3V0ICAo0YLQvtC70YzQutC+INC+0L0sINC90LjRh9C10LPQviDQsdC+0LvRjNGI0LUpCiAgKiDQu9C+0LPQuCDQuCDQv9GA0L7Qs9GA0LXRgdGBIC0+IHN0ZGVycgogICog0LvRjtCx0L7QuSDRgdC60YDQuNC/0YIg0YPQvNC10LXRgiDRh9C40YLQsNGC0Ywg0YHQviBzdGRpbiDRgtCw0LrQvtC5INC20LUg0LrQvtC90LLQtdGA0YIg0Lgg0LTQvtGB0YLQsNGC0Ywg0L7RgtGC0YPQtNCwINGG0LXQu9C4CgrQpNC+0YDQvNCwINC60L7QvdCy0LXRgNGC0LA6OgoKICAgIHsKICAgICAgInNjaGVtYSI6ICJjeWJlcmRlY2sudjEiLAogICAgICAidG9vbCI6ICJwb3J0c2NhbiIsCiAgICAgICJydW5faWQiOiAiYTFiMmMzZDRlNWY2IiwKICAgICAgInN0YXR1cyI6ICJvayIgfCAicGFydGlhbCIgfCAiZXJyb3IiLAogICAgICAic3RhcnRlZF9hdCI6ICIuLi4iLCAiZmluaXNoZWRfYXQiOiAiLi4uIiwgImR1cmF0aW9uX3NlYyI6IDEyLjMsCiAgICAgICJwYXJhbXMiOiB7Li4ufSwgICAgICAgICAgICAgICAgICMg0YfQtdC8INC40LzQtdC90L3QviDQt9Cw0L/Rg9GB0LrQsNC70LgKICAgICAgInRhcmdldHMiOiBbIjEwLjAuMC4xIl0sICAgICAgICAgIyDRh9GC0L4g0L/RgNC+0YHQuNC70Lgg0L/RgNC+0YHQutCw0L3QuNGA0L7QstCw0YLRjAogICAgICAiaG9zdHMiOiBbICAgICAgICAgICAgICAgICAgICAgICAjINCz0LvQsNCy0L3Ri9C5INC90L7RgdC40YLQtdC70Ywg0LTQsNC90L3Ri9GFINGG0LXQv9C+0YfQutC4CiAgICAgICAgeyJpcCI6ICIxMC4wLjAuMSIsICJob3N0bmFtZXMiOiBbLi4uXSwgInN0YXRlIjogInVwIiwKICAgICAgICAgInBvcnRzIjogW3sicG9ydCI6IDIyLCAicHJvdG8iOiAidGNwIiwgInN0YXRlIjogIm9wZW4iLAogICAgICAgICAgICAgICAgICAgICJzZXJ2aWNlIjogInNzaCIsICJwcm9kdWN0IjogIk9wZW5TU0giLCAidmVyc2lvbiI6ICI5LjZwMSIsCiAgICAgICAgICAgICAgICAgICAgImNwZSI6IFsuLi5dLCAic2NyaXB0cyI6IHsuLi59LCAic291cmNlIjogIm5tYXAifV19CiAgICAgIF0sCiAgICAgICJzdGF0cyI6IHsuLi59LAogICAgICAid2FybmluZ3MiOiBbXSwgImVycm9ycyI6IFtdCiAgICB9CgrQmtC70Y7RhyBgYGhvc3RzYGAg4oCUINC+0LHRidC40Lkg0LTQu9GPINCy0YHQtdCz0L4g0L3QsNCx0L7RgNCwINGB0LrRgNC40L/RgtC+0LIsINC/0L7RjdGC0L7QvNGDINGB0LvQtdC00YPRjtGJ0LjQuSDQuNC90YHRgtGA0YPQvNC10L3RggrQsiDRhtC10L/QvtGH0LrQtSAoaHR0cC3Qv9GA0L7QsdCwLCDQsdGA0YPRgtGE0L7RgNGBINCx0LDQvdC90LXRgNC+0LIg0Lgg0YIu0LQuKSDRh9C40YLQsNC10YIg0LXQs9C+LCDQtNC+0L/QvtC70L3Rj9C10YIg0YHQstC+0LjQvNC4CtC/0L7Qu9GP0LzQuCDQuCDQvtGC0LTQsNGR0YIg0LTQsNC70YzRiNC1INCyINGC0L7QvCDQttC1INCy0LjQtNC1LgoiIiIKCmZyb20gX19mdXR1cmVfXyBpbXBvcnQgYW5ub3RhdGlvbnMKCmltcG9ydCBkYXRldGltZSBhcyBkdAppbXBvcnQganNvbgppbXBvcnQgdGltZQppbXBvcnQgdXVpZApmcm9tIHR5cGluZyBpbXBvcnQgQW55LCBDYWxsYWJsZSwgSXRlcmFibGUKClNDSEVNQSA9ICJjeWJlcmRlY2sudjEiCgoKZGVmIF9ub3coKSAtPiBzdHI6CiAgICByZXR1cm4gZHQuZGF0ZXRpbWUubm93KGR0LnRpbWV6b25lLnV0YykuaXNvZm9ybWF0KHRpbWVzcGVjPSJzZWNvbmRzIikKCgpkZWYgbWFrZV9wb3J0KAogICAgcG9ydDogaW50LAogICAgcHJvdG86IHN0ciA9ICJ0Y3AiLAogICAgc3RhdGU6IHN0ciA9ICJvcGVuIiwKICAgIHNvdXJjZTogc3RyID0gIiIsCiAgICAqKmV4dHJhOiBBbnksCikgLT4gZGljdDoKICAgICIiItCf0L7RgNGCINCyINC60LDQvdC+0L3QuNGH0L3QvtC8INCy0LjQtNC1LiDQn9GD0YHRgtGL0LUg0L/QvtC70Y8g0L3QtSDRgtCw0YnQuNC8IOKAlCDQutC+0L3QstC10YDRgiDQtNC+0LvQttC10L0g0LHRi9GC0Ywg0YfQuNGC0LDQtdC80YvQvC4iIiIKICAgIHJlYzogZGljdFtzdHIsIEFueV0gPSB7InBvcnQiOiBpbnQocG9ydCksICJwcm90byI6IHByb3RvLCAic3RhdGUiOiBzdGF0ZX0KICAgIGlmIHNvdXJjZToKICAgICAgICByZWNbInNvdXJjZSJdID0gc291cmNlCiAgICBmb3Iga2V5LCB2YWx1ZSBpbiBleHRyYS5pdGVtcygpOgogICAgICAgIGlmIHZhbHVlIG5vdCBpbiAoTm9uZSwgIiIsIFtdLCB7fSk6CiAgICAgICAgICAgIHJlY1trZXldID0gdmFsdWUKICAgIHJldHVybiByZWMKCgpjbGFzcyBFbnZlbG9wZToKICAgICIiItCd0LDQutC+0L/QuNGC0LXQu9GMINGA0LXQt9GD0LvRjNGC0LDRgtCwINC+0LTQvdC+0LPQviDQt9Cw0L/Rg9GB0LrQsC4iIiIKCiAgICBkZWYgX19pbml0X18oc2VsZiwgdG9vbDogc3RyLCB0b29sX3ZlcnNpb246IHN0ciwgcGFyYW1zOiBkaWN0IHwgTm9uZSA9IE5vbmUpOgogICAgICAgIHNlbGYudG9vbCA9IHRvb2wKICAgICAgICBzZWxmLnRvb2xfdmVyc2lvbiA9IHRvb2xfdmVyc2lvbgogICAgICAgIHNlbGYucnVuX2lkID0gdXVpZC51dWlkNCgpLmhleFs6MTJdCiAgICAgICAgc2VsZi5zdGFydGVkX2F0ID0gX25vdygpCiAgICAgICAgc2VsZi5fdDAgPSB0aW1lLm1vbm90b25pYygpCiAgICAgICAgc2VsZi5wYXJhbXMgPSBwYXJhbXMgb3Ige30KICAgICAgICBzZWxmLnRhcmdldHM6IGxpc3Rbc3RyXSA9IFtdCiAgICAgICAgc2VsZi5zdGF0dXMgPSAib2siCiAgICAgICAgc2VsZi53YXJuaW5nczogbGlzdFtzdHJdID0gW10KICAgICAgICBzZWxmLmVycm9yczogbGlzdFtzdHJdID0gW10KICAgICAgICBzZWxmLl9ob3N0czogZGljdFtzdHIsIGRpY3RdID0ge30KICAgICAgICBzZWxmLl9zdGF0c19leHRyYTogZGljdFtzdHIsIEFueV0gPSB7fQoKICAgICMgLS0g0L3QsNC/0L7Qu9C90LXQvdC40LUgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCgogICAgZGVmIGhvc3Qoc2VsZiwgaXA6IHN0cikgLT4gZGljdDoKICAgICAgICAiIiLQlNC+0YHRgtCw0YLRjCDQuNC70Lgg0LfQsNCy0LXRgdGC0Lgg0LfQsNC/0LjRgdGMINGF0L7RgdGC0LAuIiIiCiAgICAgICAgcmVjID0gc2VsZi5faG9zdHMuZ2V0KGlwKQogICAgICAgIGlmIHJlYyBpcyBOb25lOgogICAgICAgICAgICByZWMgPSB7ImlwIjogaXAsICJob3N0bmFtZXMiOiBbXSwgInN0YXRlIjogInVua25vd24iLCAicG9ydHMiOiBbXX0KICAgICAgICAgICAgc2VsZi5faG9zdHNbaXBdID0gcmVjCiAgICAgICAgcmV0dXJuIHJlYwoKICAgIGRlZiBhZGRfcG9ydChzZWxmLCBpcDogc3RyLCBwb3J0OiBkaWN0KSAtPiBkaWN0OgogICAgICAgICIiItCU0L7QsdCw0LLQuNGC0Ywg0L/QvtGA0YIg0YXQvtGB0YLRgyDQu9C40LHQviDQvtCx0L7Qs9Cw0YLQuNGC0Ywg0YPQttC1INC40LfQstC10YHRgtC90YvQuSAobm1hcCDQv9C+0LLQtdGA0YUgbWFzc2NhbikuIiIiCiAgICAgICAgaG9zdCA9IHNlbGYuaG9zdChpcCkKICAgICAgICBrZXkgPSAocG9ydFsicHJvdG8iXSwgcG9ydFsicG9ydCJdKQogICAgICAgIGZvciBleGlzdGluZyBpbiBob3N0WyJwb3J0cyJdOgogICAgICAgICAgICBpZiAoZXhpc3RpbmdbInByb3RvIl0sIGV4aXN0aW5nWyJwb3J0Il0pID09IGtleToKICAgICAgICAgICAgICAgIGV4aXN0aW5nLnVwZGF0ZShwb3J0KQogICAgICAgICAgICAgICAgcmV0dXJuIGV4aXN0aW5nCiAgICAgICAgaG9zdFsicG9ydHMiXS5hcHBlbmQocG9ydCkKICAgICAgICByZXR1cm4gcG9ydAoKICAgIGRlZiBhZGRfc3RhdChzZWxmLCBrZXk6IHN0ciwgdmFsdWU6IEFueSkgLT4gTm9uZToKICAgICAgICAiIiLQlNC+0YHRi9C/0LDRgtGMINGB0LLQvtGRINC/0L7Qu9C1INCyIGBgc3RhdHNgYCAo0LPRgNGD0L/Qv9C40YDQvtCy0LrQuCwg0YHRh9GR0YLRh9C40LrQuCDQutC+0L3QutGA0LXRgtC90L7Qs9C+INGC0YPQu9CwKS4KCiAgICAgICAg0JHQsNC30L7QstGL0LUg0L/QvtC70Y8gKHRhcmdldHMvaG9zdHNfd2l0aF9wb3J0cy9vcGVuX3BvcnRzKSDQvtGB0YLQsNGO0YLRgdGPLCDQutCw0YHRgtC+0LzQvdGL0LUKICAgICAgICDQv9GA0L7RgdGC0L4g0LzQtdGA0LbQsNGC0YHRjyDRgdCy0LXRgNGF0YMg4oCUINGC0LDQuiDQutCw0LbQtNGL0Lkg0YHQutGA0LjQv9GCINC60LvQsNC00ZHRgiDQsiDQutC+0L3QstC10YDRgiDRgdCy0L7RjiDRgdCy0L7QtNC60YMsCiAgICAgICAg0L3QtSDRgtGA0L7Qs9Cw0Y8g0L7QsdGJ0LjQuSDQutC+0L3RgtGA0LDQutGCLgogICAgICAgICIiIgogICAgICAgIHNlbGYuX3N0YXRzX2V4dHJhW2tleV0gPSB2YWx1ZQoKICAgIGRlZiBmaWx0ZXJfaG9zdHMoc2VsZiwga2VlcDogQ2FsbGFibGVbW2RpY3RdLCBib29sXSkgLT4gaW50OgogICAgICAgICIiItCe0YHRgtCw0LLQuNGC0Ywg0YLQvtC70YzQutC+INGF0L7RgdGC0YssINC00LvRjyDQutC+0YLQvtGA0YvRhSBgYGtlZXAoaG9zdClgYCDQuNGB0YLQuNC90L3Qvi4KCiAgICAgICAg0JLQvtC30LLRgNCw0YnQsNC10YIsINGB0LrQvtC70YzQutC+INGF0L7RgdGC0L7QsiDRg9Cx0YDQsNC70LggKNC90LDQv9GA0LjQvNC10YAsIGBgLS1hbGl2ZS1vbmx5YGAg0LIg0YHQutCw0L3QtdGA0LUpLgogICAgICAgICIiIgogICAgICAgIGJlZm9yZSA9IGxlbihzZWxmLl9ob3N0cykKICAgICAgICBzZWxmLl9ob3N0cyA9IHtpcDogaCBmb3IgaXAsIGggaW4gc2VsZi5faG9zdHMuaXRlbXMoKSBpZiBrZWVwKGgpfQogICAgICAgIHJldHVybiBiZWZvcmUgLSBsZW4oc2VsZi5faG9zdHMpCgogICAgZGVmIHdhcm4oc2VsZiwgbWVzc2FnZTogc3RyKSAtPiBOb25lOgogICAgICAgIHNlbGYud2FybmluZ3MuYXBwZW5kKG1lc3NhZ2UpCgogICAgZGVmIGZhaWwoc2VsZiwgbWVzc2FnZTogc3RyKSAtPiBOb25lOgogICAgICAgIHNlbGYuZXJyb3JzLmFwcGVuZChtZXNzYWdlKQogICAgICAgIHNlbGYuc3RhdHVzID0gImVycm9yIgoKICAgICMgLS0g0LLRi9Cz0YDRg9C30LrQsCAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQoKICAgIEBwcm9wZXJ0eQogICAgZGVmIGhvc3RzKHNlbGYpIC0+IGxpc3RbZGljdF06CiAgICAgICAgcmV0dXJuIFtzZWxmLl9ob3N0c1tpcF0gZm9yIGlwIGluIHNvcnRlZChzZWxmLl9ob3N0cyldCgogICAgZGVmIHRvX2RpY3Qoc2VsZikgLT4gZGljdDoKICAgICAgICBob3N0cyA9IHNlbGYuaG9zdHMKICAgICAgICBmb3IgaG9zdCBpbiBob3N0czoKICAgICAgICAgICAgaG9zdFsicG9ydHMiXS5zb3J0KGtleT1sYW1iZGEgcDogKHBbInByb3RvIl0sIHBbInBvcnQiXSkpCiAgICAgICAgb3Blbl9wb3J0cyA9IHN1bSgKICAgICAgICAgICAgMSBmb3IgaCBpbiBob3N0cyBmb3IgcCBpbiBoWyJwb3J0cyJdIGlmIHAuZ2V0KCJzdGF0ZSIpID09ICJvcGVuIgogICAgICAgICkKICAgICAgICByZXR1cm4gewogICAgICAgICAgICAic2NoZW1hIjogU0NIRU1BLAogICAgICAgICAgICAidG9vbCI6IHNlbGYudG9vbCwKICAgICAgICAgICAgInRvb2xfdmVyc2lvbiI6IHNlbGYudG9vbF92ZXJzaW9uLAogICAgICAgICAgICAicnVuX2lkIjogc2VsZi5ydW5faWQsCiAgICAgICAgICAgICJzdGF0dXMiOiBzZWxmLnN0YXR1cywKICAgICAgICAgICAgInN0YXJ0ZWRfYXQiOiBzZWxmLnN0YXJ0ZWRfYXQsCiAgICAgICAgICAgICJmaW5pc2hlZF9hdCI6IF9ub3coKSwKICAgICAgICAgICAgImR1cmF0aW9uX3NlYyI6IHJvdW5kKHRpbWUubW9ub3RvbmljKCkgLSBzZWxmLl90MCwgMiksCiAgICAgICAgICAgICJwYXJhbXMiOiBzZWxmLnBhcmFtcywKICAgICAgICAgICAgInRhcmdldHMiOiBzZWxmLnRhcmdldHMsCiAgICAgICAgICAgICJob3N0cyI6IGhvc3RzLAogICAgICAgICAgICAic3RhdHMiOiB7CiAgICAgICAgICAgICAgICAidGFyZ2V0cyI6IGxlbihzZWxmLnRhcmdldHMpLAogICAgICAgICAgICAgICAgImhvc3RzX3dpdGhfcG9ydHMiOiBzdW0oMSBmb3IgaCBpbiBob3N0cyBpZiBoWyJwb3J0cyJdKSwKICAgICAgICAgICAgICAgICJvcGVuX3BvcnRzIjogb3Blbl9wb3J0cywKICAgICAgICAgICAgICAgICoqc2VsZi5fc3RhdHNfZXh0cmEsCiAgICAgICAgICAgIH0sCiAgICAgICAgICAgICJ3YXJuaW5ncyI6IHNlbGYud2FybmluZ3MsCiAgICAgICAgICAgICJlcnJvcnMiOiBzZWxmLmVycm9ycywKICAgICAgICB9CgogICAgZGVmIHRvX2pzb24oc2VsZiwgaW5kZW50OiBpbnQgfCBOb25lID0gMikgLT4gc3RyOgogICAgICAgIHJldHVybiBqc29uLmR1bXBzKHNlbGYudG9fZGljdCgpLCBlbnN1cmVfYXNjaWk9RmFsc2UsIGluZGVudD1pbmRlbnQpCgoKY2xhc3MgSW5wdXQ6CiAgICAiIiLQotC+LCDRh9GC0L4g0L/RgNC40YjQu9C+INC90LAg0LLRhdC+0LQ6INGG0LXQu9C4INC4ICjQvtC/0YbQuNC+0L3QsNC70YzQvdC+KSDRg9C20LUg0LjQt9Cy0LXRgdGC0L3Ri9C1INC/0L7RgNGC0YsuIiIiCgogICAgZGVmIF9faW5pdF9fKHNlbGYsIHRhcmdldHM6IEl0ZXJhYmxlW3N0cl0gPSAoKSwgaG9zdHM6IEl0ZXJhYmxlW2RpY3RdID0gKCkpOgogICAgICAgIHNlbGYudGFyZ2V0cyA9IGxpc3QoZGljdC5mcm9ta2V5cyh0YXJnZXRzKSkKICAgICAgICBzZWxmLmhvc3RzID0gbGlzdChob3N0cykKCiAgICBkZWYgX19ib29sX18oc2VsZikgLT4gYm9vbDoKICAgICAgICByZXR1cm4gYm9vbChzZWxmLnRhcmdldHMgb3Igc2VsZi5ob3N0cykKCgpkZWYgcmVhZF9pbnB1dCh0ZXh0OiBzdHIpIC0+IElucHV0OgogICAgIiIi0KDQsNC30L7QsdGA0LDRgtGMIHN0ZGluLgoKICAgINCf0L7QvdC40LzQsNC10YI6INC60L7QvdCy0LXRgNGCIGN5YmVyZGVjay52MSwg0LPQvtC70YvQuSDRgdC/0LjRgdC+0Log0YHRgtGA0L7Qui/QvtCx0YrQtdC60YLQvtCyINCyIEpTT04g0LgKICAgINC/0YDQvtGB0YLQviDQv9C+0YHRgtGA0L7Rh9C90YvQuSDRgdC/0LjRgdC+0Log0LDQtNGA0LXRgdC+0LIg4oCUINGH0YLQvtCx0Ysg0LTQtdC60LAg0LTRgNGD0LbQuNC70LAg0YEg0L7QsdGL0YfQvdGL0Lwg0YLQtdC60YHRgtC+0LwuCiAgICAiIiIKICAgIHRleHQgPSB0ZXh0LnN0cmlwKCkKICAgIGlmIG5vdCB0ZXh0OgogICAgICAgIHJldHVybiBJbnB1dCgpCgogICAgdHJ5OgogICAgICAgIHBheWxvYWQgPSBqc29uLmxvYWRzKHRleHQpCiAgICBleGNlcHQganNvbi5KU09ORGVjb2RlRXJyb3I6CiAgICAgICAgdGFyZ2V0cyA9IFsKICAgICAgICAgICAgbGluZS5zdHJpcCgpCiAgICAgICAgICAgIGZvciBsaW5lIGluIHRleHQuc3BsaXRsaW5lcygpCiAgICAgICAgICAgIGlmIGxpbmUuc3RyaXAoKSBhbmQgbm90IGxpbmUubHN0cmlwKCkuc3RhcnRzd2l0aCgiIyIpCiAgICAgICAgXQogICAgICAgIHJldHVybiBJbnB1dCh0YXJnZXRzPXRhcmdldHMpCgogICAgaWYgaXNpbnN0YW5jZShwYXlsb2FkLCBsaXN0KToKICAgICAgICB0YXJnZXRzLCBob3N0cyA9IFtdLCBbXQogICAgICAgIGZvciBpdGVtIGluIHBheWxvYWQ6CiAgICAgICAgICAgIGlmIGlzaW5zdGFuY2UoaXRlbSwgc3RyKToKICAgICAgICAgICAgICAgIHRhcmdldHMuYXBwZW5kKGl0ZW0pCiAgICAgICAgICAgIGVsaWYgaXNpbnN0YW5jZShpdGVtLCBkaWN0KSBhbmQgaXRlbS5nZXQoImlwIik6CiAgICAgICAgICAgICAgICBob3N0cy5hcHBlbmQoaXRlbSkKICAgICAgICAgICAgICAgIHRhcmdldHMuYXBwZW5kKGl0ZW1bImlwIl0pCiAgICAgICAgcmV0dXJuIElucHV0KHRhcmdldHM9dGFyZ2V0cywgaG9zdHM9aG9zdHMpCgogICAgaWYgaXNpbnN0YW5jZShwYXlsb2FkLCBkaWN0KToKICAgICAgICBob3N0cyA9IFtoIGZvciBoIGluIHBheWxvYWQuZ2V0KCJob3N0cyIsIFtdKSBpZiBpc2luc3RhbmNlKGgsIGRpY3QpIGFuZCBoLmdldCgiaXAiKV0KICAgICAgICB0YXJnZXRzID0gbGlzdChwYXlsb2FkLmdldCgidGFyZ2V0cyIpIG9yIFtdKQogICAgICAgIHRhcmdldHMgKz0gW2hbImlwIl0gZm9yIGggaW4gaG9zdHNdCiAgICAgICAgcmV0dXJuIElucHV0KHRhcmdldHM9dGFyZ2V0cywgaG9zdHM9aG9zdHMpCgogICAgcmV0dXJuIElucHV0KCk=')
_cd('cyberdeck.ui', 'IiIi0JrQvtC90YHQvtC70YzQvdGL0Lkg0LLRi9Cy0L7QtCDQtNC10LrQuC4KCtCS0YHRkSDQvtGE0L7RgNC80LvQtdC90LjQtSDRg9GF0L7QtNC40YIg0LIgc3RkZXJyLCDRh9GC0L7QsdGLIHN0ZG91dCDQvtGB0YLQsNCy0LDQu9GB0Y8g0YfQuNGB0YLRi9C8INC60LDQvdCw0LvQvtC8INC00LDQvdC90YvRhQrQtNC70Y8g0L/QsNC50L/QvtCyLiDQmtGA0LDRgdC40LLQviDigJQg0LXRgdC70Lgg0YHRgtC+0LjRgiByaWNoOyDQsdC10Lcg0L3QtdCz0L4g0YHQutGA0LjQv9GCINCy0YHRkSDRgNCw0LLQvdC+INGA0LDQsdC+0YLQsNC10YIuCiIiIgoKZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwoKaW1wb3J0IHN5cwpmcm9tIGNvbnRleHRsaWIgaW1wb3J0IGNvbnRleHRtYW5hZ2VyCgp0cnk6CiAgICBmcm9tIHJpY2guY29uc29sZSBpbXBvcnQgQ29uc29sZQogICAgZnJvbSByaWNoLnByb2dyZXNzIGltcG9ydCAoCiAgICAgICAgQmFyQ29sdW1uLAogICAgICAgIFByb2dyZXNzLAogICAgICAgIFNwaW5uZXJDb2x1bW4sCiAgICAgICAgVGV4dENvbHVtbiwKICAgICAgICBUaW1lRWxhcHNlZENvbHVtbiwKICAgICkKICAgIGZyb20gcmljaC50YWJsZSBpbXBvcnQgVGFibGUKCiAgICBIQVNfUklDSCA9IFRydWUKZXhjZXB0IEltcG9ydEVycm9yOiAgIyDQs9C+0LvQsNGPINGB0LjRgdGC0LXQvNCwIOKAlCDRgNCw0LHQvtGC0LDQtdC8INGC0LXQutGB0YLQvtC8CiAgICBIQVNfUklDSCA9IEZhbHNlCgoKZGVmIGZvcmNlX3V0ZjgoKSAtPiBOb25lOgogICAgIiIiVVRGLTgg0L3QsCDQstGB0LXRhSDRgtGA0ZHRhSDQv9C+0YLQvtC60LDRhTog0LrQuNGA0LjQu9C70LjRhtCwL9GN0LzQvtC00LfQuCDQvdC1INC00L7Qu9C20L3RiyDQv9Cw0LTQsNGC0Ywg0L3QsCBjcDEyNTIvY3A4NjYuCgogICAgc3RkaW4g0YLQvtC20LU6INC60L7QvdCy0LXRgNGC0Ysg0LrQuNCx0LXRgNC00LXQutC4INGF0L7QtNGP0YIg0L/QviDQv9Cw0LnQv9Cw0Lwg0LIgVVRGLTggKHJlbWFyayfQuCBWTEVTUyDigJQg0YEKICAgINGN0LzQvtC00LfQuCksINCwIFdpbmRvd3Mg0L/QviDRg9C80L7Qu9GH0LDQvdC40Y4g0YfQuNGC0LDQtdGCIHN0ZGluINCyIGNwMTI1MiDQuCDQutC+0YDRkdC20LjRgiDQuNGFLgogICAgIiIiCiAgICBmb3Igc3RyZWFtIGluIChzeXMuc3RkaW4sIHN5cy5zdGRvdXQsIHN5cy5zdGRlcnIpOgogICAgICAgIHJlY29uZmlndXJlID0gZ2V0YXR0cihzdHJlYW0sICJyZWNvbmZpZ3VyZSIsIE5vbmUpCiAgICAgICAgaWYgcmVjb25maWd1cmUgaXMgbm90IE5vbmU6CiAgICAgICAgICAgIHRyeToKICAgICAgICAgICAgICAgIHJlY29uZmlndXJlKGVuY29kaW5nPSJ1dGYtOCIsIGVycm9ycz0icmVwbGFjZSIpCiAgICAgICAgICAgIGV4Y2VwdCAoVmFsdWVFcnJvciwgT1NFcnJvcik6CiAgICAgICAgICAgICAgICBwYXNzCgoKY2xhc3MgX1BsYWluUHJvZ3Jlc3M6CiAgICAiIiLQl9Cw0LPQu9GD0YjQutCwINC/0YDQvtCz0YDQtdGB0YHQsDog0L/QtdGH0LDRgtCw0LXRgiDQstC10YXQuCDQv9C+IDEwJSwg0L3QtSDQt9Cw0YHQvtGA0Y/RjyDQu9C+0LMuIiIiCgogICAgZGVmIF9faW5pdF9fKHNlbGYsIHVpOiAiVUkiKToKICAgICAgICBzZWxmLl91aSA9IHVpCiAgICAgICAgc2VsZi5fdGFza3M6IGRpY3RbaW50LCB0dXBsZVtzdHIsIGZsb2F0XV0gPSB7fQogICAgICAgIHNlbGYuX25leHQgPSAwCgogICAgZGVmIGFkZChzZWxmLCBkZXNjcmlwdGlvbjogc3RyLCB0b3RhbDogZmxvYXQgfCBOb25lID0gMTAwLjApIC0+IGludDoKICAgICAgICB0YXNrX2lkID0gc2VsZi5fbmV4dAogICAgICAgIHNlbGYuX25leHQgKz0gMQogICAgICAgIHNlbGYuX3Rhc2tzW3Rhc2tfaWRdID0gKGRlc2NyaXB0aW9uLCAtMS4wKQogICAgICAgIHNlbGYuX3VpLmluZm8oZGVzY3JpcHRpb24pCiAgICAgICAgcmV0dXJuIHRhc2tfaWQKCiAgICBkZWYgdXBkYXRlKHNlbGYsIHRhc2tfaWQ6IGludCwgY29tcGxldGVkOiBmbG9hdCB8IE5vbmUgPSBOb25lLCBkZXNjcmlwdGlvbjogc3RyIHwgTm9uZSA9IE5vbmUsICoqXzogb2JqZWN0KSAtPiBOb25lOgogICAgICAgIGRlc2MsIGxhc3QgPSBzZWxmLl90YXNrcy5nZXQodGFza19pZCwgKCIiLCAtMS4wKSkKICAgICAgICBpZiBkZXNjcmlwdGlvbiBpcyBub3QgTm9uZToKICAgICAgICAgICAgZGVzYyA9IGRlc2NyaXB0aW9uCiAgICAgICAgaWYgY29tcGxldGVkIGlzIG5vdCBOb25lIGFuZCBjb21wbGV0ZWQgLSBsYXN0ID49IDEwOgogICAgICAgICAgICBsYXN0ID0gY29tcGxldGVkCiAgICAgICAgICAgIHNlbGYuX3VpLmRpbShmIntkZXNjfSDigJQge2NvbXBsZXRlZDouMGZ9JSIpCiAgICAgICAgc2VsZi5fdGFza3NbdGFza19pZF0gPSAoZGVzYywgbGFzdCkKCiAgICBkZWYgbG9nKHNlbGYsIG1lc3NhZ2U6IHN0cikgLT4gTm9uZToKICAgICAgICBzZWxmLl91aS5yYXcobWVzc2FnZSkKCgpjbGFzcyBfUmljaFByb2dyZXNzOgogICAgZGVmIF9faW5pdF9fKHNlbGYsIHByb2dyZXNzOiAiUHJvZ3Jlc3MiKToKICAgICAgICBzZWxmLl9wID0gcHJvZ3Jlc3MKCiAgICBkZWYgYWRkKHNlbGYsIGRlc2NyaXB0aW9uOiBzdHIsIHRvdGFsOiBmbG9hdCB8IE5vbmUgPSAxMDAuMCkgLT4gaW50OgogICAgICAgIHJldHVybiBzZWxmLl9wLmFkZF90YXNrKGRlc2NyaXB0aW9uLCB0b3RhbD10b3RhbCwgbm90ZT0iIikKCiAgICBkZWYgdXBkYXRlKHNlbGYsIHRhc2tfaWQ6IGludCwgKiprd2FyZ3M6IG9iamVjdCkgLT4gTm9uZToKICAgICAgICBzZWxmLl9wLnVwZGF0ZSh0YXNrX2lkLCAqKmt3YXJncykKCiAgICBkZWYgbG9nKHNlbGYsIG1lc3NhZ2U6IHN0cikgLT4gTm9uZToKICAgICAgICAjINC/0LXRh9Cw0YLRjCDRh9C10YDQtdC3IHByb2dyZXNzLmNvbnNvbGUg0L3QtSDQu9C+0LzQsNC10YIg0LbQuNCy0L7QuSDQsdCw0YAKICAgICAgICBzZWxmLl9wLmNvbnNvbGUucHJpbnQobWVzc2FnZSwgaGlnaGxpZ2h0PUZhbHNlKQoKCmNsYXNzIFVJOgogICAgZGVmIF9faW5pdF9fKHNlbGYsIHF1aWV0OiBib29sID0gRmFsc2UsIHZlcmJvc2U6IGJvb2wgPSBGYWxzZSwgY29sb3I6IGJvb2wgPSBUcnVlKToKICAgICAgICBzZWxmLnF1aWV0ID0gcXVpZXQKICAgICAgICBzZWxmLnZlcmJvc2UgPSB2ZXJib3NlCiAgICAgICAgaWYgSEFTX1JJQ0g6CiAgICAgICAgICAgIGZvcmNlID0gTm9uZSBpZiBjb2xvciBlbHNlIEZhbHNlCiAgICAgICAgICAgIHNlbGYuZXJyID0gQ29uc29sZShzdGRlcnI9VHJ1ZSwgZm9yY2VfdGVybWluYWw9Zm9yY2UsIG5vX2NvbG9yPW5vdCBjb2xvcikKICAgICAgICAgICAgc2VsZi5vdXQgPSBDb25zb2xlKGZvcmNlX3Rlcm1pbmFsPWZvcmNlLCBub19jb2xvcj1ub3QgY29sb3IpCiAgICAgICAgZWxzZToKICAgICAgICAgICAgc2VsZi5lcnIgPSBzZWxmLm91dCA9IE5vbmUKCiAgICAjIC0tINC/0YDQuNC80LjRgtC40LLRiyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCgogICAgZGVmIF9lbWl0KHNlbGYsIHBsYWluOiBzdHIsIG1hcmt1cDogc3RyKSAtPiBOb25lOgogICAgICAgIGlmIHNlbGYucXVpZXQ6CiAgICAgICAgICAgIHJldHVybgogICAgICAgIGlmIEhBU19SSUNIOgogICAgICAgICAgICBzZWxmLmVyci5wcmludChtYXJrdXAsIGhpZ2hsaWdodD1GYWxzZSkKICAgICAgICBlbHNlOgogICAgICAgICAgICBwcmludChwbGFpbiwgZmlsZT1zeXMuc3RkZXJyLCBmbHVzaD1UcnVlKQoKICAgIGRlZiBpbmZvKHNlbGYsIG1lc3NhZ2U6IHN0cikgLT4gTm9uZToKICAgICAgICBzZWxmLl9lbWl0KGYiWypdIHttZXNzYWdlfSIsIGYiW2JvbGQgY3lhbl1cXFsqXVsvXSB7bWVzc2FnZX0iKQoKICAgIGRlZiBvayhzZWxmLCBtZXNzYWdlOiBzdHIpIC0+IE5vbmU6CiAgICAgICAgc2VsZi5fZW1pdChmIlsrXSB7bWVzc2FnZX0iLCBmIltib2xkIGdyZWVuXVxcWytdWy9dIHttZXNzYWdlfSIpCgogICAgZGVmIHdhcm4oc2VsZiwgbWVzc2FnZTogc3RyKSAtPiBOb25lOgogICAgICAgIHNlbGYuX2VtaXQoZiJbIV0ge21lc3NhZ2V9IiwgZiJbYm9sZCB5ZWxsb3ddXFxbIV1bL10ge21lc3NhZ2V9IikKCiAgICBkZWYgZXJyX21zZyhzZWxmLCBtZXNzYWdlOiBzdHIpIC0+IE5vbmU6CiAgICAgICAgIyDQvtGI0LjQsdC60Lgg0LLQuNC00L3QviDQtNCw0LbQtSDQsiBxdWlldCDigJQg0LzQvtC70YfQsNGC0Ywg0L/RgNC+INC90LjRhSDQvdC10LvRjNC30Y8KICAgICAgICBpZiBIQVNfUklDSDoKICAgICAgICAgICAgc2VsZi5lcnIucHJpbnQoZiJbYm9sZCByZWRdXFxbeF1bL10ge21lc3NhZ2V9IiwgaGlnaGxpZ2h0PUZhbHNlKQogICAgICAgIGVsc2U6CiAgICAgICAgICAgIHByaW50KGYiW3hdIHttZXNzYWdlfSIsIGZpbGU9c3lzLnN0ZGVyciwgZmx1c2g9VHJ1ZSkKCiAgICBkZWYgZGltKHNlbGYsIG1lc3NhZ2U6IHN0cikgLT4gTm9uZToKICAgICAgICBzZWxmLl9lbWl0KGYiICAgIHttZXNzYWdlfSIsIGYiW2RpbV0gICAge21lc3NhZ2V9Wy9dIikKCiAgICBkZWYgcmF3KHNlbGYsIG1lc3NhZ2U6IHN0cikgLT4gTm9uZToKICAgICAgICAiIiLQodGL0YDQsNGPINGB0YLRgNC+0LrQsCDQstC90LXRiNC90LXQs9C+INC40L3RgdGC0YDRg9C80LXQvdGC0LAgKNGC0L7Qu9GM0LrQviDQv9GA0LggLS12ZXJib3NlKS4iIiIKICAgICAgICBpZiBzZWxmLnZlcmJvc2U6CiAgICAgICAgICAgIHNlbGYuX2VtaXQoZiIgIHwge21lc3NhZ2V9IiwgZiJbZGltXSAg4pSCIHttZXNzYWdlfVsvXSIpCgogICAgZGVmIGJhbm5lcihzZWxmLCB0aXRsZTogc3RyLCBzdWJ0aXRsZTogc3RyID0gIiIpIC0+IE5vbmU6CiAgICAgICAgaWYgc2VsZi5xdWlldDoKICAgICAgICAgICAgcmV0dXJuCiAgICAgICAgaWYgSEFTX1JJQ0g6CiAgICAgICAgICAgIHNlbGYuZXJyLnByaW50KCkKICAgICAgICAgICAgc2VsZi5lcnIucnVsZShmIltib2xkIG1hZ2VudGFde3RpdGxlfVsvXSIgKyAoZiIgW2RpbV17c3VidGl0bGV9Wy9dIiBpZiBzdWJ0aXRsZSBlbHNlICIiKSkKICAgICAgICBlbHNlOgogICAgICAgICAgICBwcmludChmIlxuPT09IHt0aXRsZX0ge3N1YnRpdGxlfSA9PT0iLCBmaWxlPXN5cy5zdGRlcnIsIGZsdXNoPVRydWUpCgogICAgZGVmIHN0YWdlKHNlbGYsIHRpdGxlOiBzdHIpIC0+IE5vbmU6CiAgICAgICAgaWYgc2VsZi5xdWlldDoKICAgICAgICAgICAgcmV0dXJuCiAgICAgICAgaWYgSEFTX1JJQ0g6CiAgICAgICAgICAgIHNlbGYuZXJyLnByaW50KGYiXG5bYm9sZCBibHVlXeKWkFsvXSBbYm9sZF17dGl0bGV9Wy9dIiwgaGlnaGxpZ2h0PUZhbHNlKQogICAgICAgIGVsc2U6CiAgICAgICAgICAgIHByaW50KGYiXG4tLSB7dGl0bGV9IiwgZmlsZT1zeXMuc3RkZXJyLCBmbHVzaD1UcnVlKQoKICAgICMgLS0g0L/RgNC+0LPRgNC10YHRgSAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQoKICAgIEBjb250ZXh0bWFuYWdlcgogICAgZGVmIHByb2dyZXNzKHNlbGYpOgogICAgICAgIGlmIG5vdCBIQVNfUklDSCBvciBzZWxmLnF1aWV0OgogICAgICAgICAgICB5aWVsZCBfUGxhaW5Qcm9ncmVzcyhzZWxmKQogICAgICAgICAgICByZXR1cm4KICAgICAgICBwcm9ncmVzcyA9IFByb2dyZXNzKAogICAgICAgICAgICBTcGlubmVyQ29sdW1uKHN0eWxlPSJtYWdlbnRhIiksCiAgICAgICAgICAgIFRleHRDb2x1bW4oIltib2xkXXt0YXNrLmRlc2NyaXB0aW9ufSIpLAogICAgICAgICAgICBCYXJDb2x1bW4oYmFyX3dpZHRoPTMyLCBjb21wbGV0ZV9zdHlsZT0iZ3JlZW4iLCBmaW5pc2hlZF9zdHlsZT0iZ3JlZW4iKSwKICAgICAgICAgICAgVGV4dENvbHVtbigiW3Byb2dyZXNzLnBlcmNlbnRhZ2Vde3Rhc2sucGVyY2VudGFnZTo+NS4xZn0lIiksCiAgICAgICAgICAgIFRpbWVFbGFwc2VkQ29sdW1uKCksCiAgICAgICAgICAgIFRleHRDb2x1bW4oInt0YXNrLmZpZWxkc1tub3RlXX0iKSwKICAgICAgICAgICAgY29uc29sZT1zZWxmLmVyciwKICAgICAgICAgICAgdHJhbnNpZW50PUZhbHNlLAogICAgICAgICkKICAgICAgICB3aXRoIHByb2dyZXNzOgogICAgICAgICAgICB5aWVsZCBfUmljaFByb2dyZXNzKHByb2dyZXNzKQoKICAgICMgLS0g0LjRgtC+0LPQvtCy0YvQuSDQvtGC0YfRkdGCIChzdGRvdXQpIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCgogICAgZGVmIHJlcG9ydChzZWxmLCBlbnZlbG9wZV9kaWN0OiBkaWN0KSAtPiBOb25lOgogICAgICAgIGhvc3RzID0gZW52ZWxvcGVfZGljdFsiaG9zdHMiXQogICAgICAgIHN0YXRzID0gZW52ZWxvcGVfZGljdFsic3RhdHMiXQoKICAgICAgICBpZiBub3QgSEFTX1JJQ0g6CiAgICAgICAgICAgIGZvciBob3N0IGluIGhvc3RzOgogICAgICAgICAgICAgICAgbmFtZSA9IGYiICh7JywgJy5qb2luKGhvc3RbJ2hvc3RuYW1lcyddKX0pIiBpZiBob3N0WyJob3N0bmFtZXMiXSBlbHNlICIiCiAgICAgICAgICAgICAgICBwcmludChmIlxue2hvc3RbJ2lwJ119e25hbWV9IOKAlCB7aG9zdFsnc3RhdGUnXX0iKQogICAgICAgICAgICAgICAgZm9yIHBvcnQgaW4gaG9zdFsicG9ydHMiXToKICAgICAgICAgICAgICAgICAgICBzZXJ2aWNlID0gcG9ydC5nZXQoInNlcnZpY2UiLCAiPyIpCiAgICAgICAgICAgICAgICAgICAgdmVyc2lvbiA9ICIgIi5qb2luKAogICAgICAgICAgICAgICAgICAgICAgICBmaWx0ZXIoTm9uZSwgW3BvcnQuZ2V0KCJwcm9kdWN0IiwgIiIpLCBwb3J0LmdldCgidmVyc2lvbiIsICIiKSwgcG9ydC5nZXQoImV4dHJhaW5mbyIsICIiKV0pCiAgICAgICAgICAgICAgICAgICAgKQogICAgICAgICAgICAgICAgICAgIHByaW50KGYiICB7cG9ydFsncG9ydCddfS97cG9ydFsncHJvdG8nXTo8M30ge3BvcnRbJ3N0YXRlJ106PDh9IHtzZXJ2aWNlOjwxNn0ge3ZlcnNpb259IikKICAgICAgICAgICAgcHJpbnQoCiAgICAgICAgICAgICAgICBmIlxu0YXQvtGB0YLQvtCyINGBINC/0L7RgNGC0LDQvNC4OiB7c3RhdHNbJ2hvc3RzX3dpdGhfcG9ydHMnXX0gICAiCiAgICAgICAgICAgICAgICBmItC+0YLQutGA0YvRgtGL0YUg0L/QvtGA0YLQvtCyOiB7c3RhdHNbJ29wZW5fcG9ydHMnXX0gICAiCiAgICAgICAgICAgICAgICBmItCy0YDQtdC80Y86IHtlbnZlbG9wZV9kaWN0WydkdXJhdGlvbl9zZWMnXX1zIgogICAgICAgICAgICApCiAgICAgICAgICAgIHJldHVybgoKICAgICAgICBmb3IgaG9zdCBpbiBob3N0czoKICAgICAgICAgICAgbmFtZSA9IGYiICBbZGltXXsnLCAnLmpvaW4oaG9zdFsnaG9zdG5hbWVzJ10pfVsvXSIgaWYgaG9zdFsiaG9zdG5hbWVzIl0gZWxzZSAiIgogICAgICAgICAgICB0YWJsZSA9IFRhYmxlKAogICAgICAgICAgICAgICAgdGl0bGU9ZiJbYm9sZCBjeWFuXXtob3N0WydpcCddfVsvXXtuYW1lfSIsCiAgICAgICAgICAgICAgICB0aXRsZV9qdXN0aWZ5PSJsZWZ0IiwKICAgICAgICAgICAgICAgIGhlYWRlcl9zdHlsZT0iYm9sZCBtYWdlbnRhIiwKICAgICAgICAgICAgICAgIGJveD1Ob25lLAogICAgICAgICAgICAgICAgcGFkX2VkZ2U9RmFsc2UsCiAgICAgICAgICAgICkKICAgICAgICAgICAgdGFibGUuYWRkX2NvbHVtbigiUE9SVCIsIHN0eWxlPSJib2xkIGdyZWVuIiwgbm9fd3JhcD1UcnVlKQogICAgICAgICAgICB0YWJsZS5hZGRfY29sdW1uKCJTVEFURSIsIG5vX3dyYXA9VHJ1ZSkKICAgICAgICAgICAgdGFibGUuYWRkX2NvbHVtbigiU0VSVklDRSIsIHN0eWxlPSJjeWFuIiwgbm9fd3JhcD1UcnVlKQogICAgICAgICAgICB0YWJsZS5hZGRfY29sdW1uKCJWRVJTSU9OIikKICAgICAgICAgICAgZm9yIHBvcnQgaW4gaG9zdFsicG9ydHMiXToKICAgICAgICAgICAgICAgIHZlcnNpb24gPSAiICIuam9pbigKICAgICAgICAgICAgICAgICAgICBmaWx0ZXIoTm9uZSwgW3BvcnQuZ2V0KCJwcm9kdWN0IiwgIiIpLCBwb3J0LmdldCgidmVyc2lvbiIsICIiKSwgcG9ydC5nZXQoImV4dHJhaW5mbyIsICIiKV0pCiAgICAgICAgICAgICAgICApCiAgICAgICAgICAgICAgICBzdGF0ZSA9IHBvcnQuZ2V0KCJzdGF0ZSIsICI/IikKICAgICAgICAgICAgICAgIHRhYmxlLmFkZF9yb3coCiAgICAgICAgICAgICAgICAgICAgZiJ7cG9ydFsncG9ydCddfS97cG9ydFsncHJvdG8nXX0iLAogICAgICAgICAgICAgICAgICAgIGYiW2dyZWVuXXtzdGF0ZX1bL10iIGlmIHN0YXRlID09ICJvcGVuIiBlbHNlIGYiW3llbGxvd117c3RhdGV9Wy9dIiwKICAgICAgICAgICAgICAgICAgICBwb3J0LmdldCgic2VydmljZSIsICItIiksCiAgICAgICAgICAgICAgICAgICAgdmVyc2lvbiBvciAiW2RpbV0tWy9dIiwKICAgICAgICAgICAgICAgICkKICAgICAgICAgICAgc2VsZi5vdXQucHJpbnQoKQogICAgICAgICAgICBzZWxmLm91dC5wcmludCh0YWJsZSkKCiAgICAgICAgc2VsZi5vdXQucHJpbnQoCiAgICAgICAgICAgIGYiXG5bYm9sZF3QuNGC0L7Qs9C+OlsvXSDRhdC+0YHRgtC+0LIg0YEg0L/QvtGA0YLQsNC80LggW2JvbGQgY3lhbl17c3RhdHNbJ2hvc3RzX3dpdGhfcG9ydHMnXX1bL10sICIKICAgICAgICAgICAgZiLQvtGC0LrRgNGL0YLRi9GFINC/0L7RgNGC0L7QsiBbYm9sZCBncmVlbl17c3RhdHNbJ29wZW5fcG9ydHMnXX1bL10sICIKICAgICAgICAgICAgZiLQstGA0LXQvNGPIFtib2xkXXtlbnZlbG9wZV9kaWN0WydkdXJhdGlvbl9zZWMnXX1zWy9dIgogICAgICAgICk=')
exec(compile(_b64.b64decode('IiIi0J7QsdGJ0LDRjyDQsdC40LHQu9C40L7RgtC10LrQsCDQutC40LHQtdGA0LTQtdC60Lg6INC10LTQuNC90YvQuSDRhNC+0YDQvNCw0YIg0LLQstC+0LTQsC/QstGL0LLQvtC00LAg0LTQu9GPINCy0YHQtdGFINGB0LrRgNC40L/RgtC+0LIuIiIiCgpmcm9tIC5lbnZlbG9wZSBpbXBvcnQgU0NIRU1BLCBFbnZlbG9wZSwgSW5wdXQsIHJlYWRfaW5wdXQsIG1ha2VfcG9ydAoKX19hbGxfXyA9IFsiU0NIRU1BIiwgIkVudmVsb3BlIiwgIklucHV0IiwgInJlYWRfaW5wdXQiLCAibWFrZV9wb3J0IiwgIl9fdmVyc2lvbl9fIl0KCl9fdmVyc2lvbl9fID0gIjAuMS4wIg==').decode('utf-8'), '<cyberdeck>', 'exec'), _cd_pkg.__dict__)
# ==== end cyberdeck inlined ====

import argparse
import base64
import getpass
import re
import secrets
import shlex
import string
import subprocess
import sys
from pathlib import Path


from cyberdeck import Envelope, read_input  # noqa: E402
from cyberdeck.ui import UI, force_utf8  # noqa: E402

force_utf8()

TOOL = "adduser"
VERSION = "0.1.0"

# useradd допускает такие имена (Debian NAME_REGEX + типичный дефолт).
RE_USERNAME = re.compile(r"^[a-z_][a-z0-9_-]{0,31}\$?$")
PW_SENTINEL = "@@CYBERDECK_PW_B64@@"
KEY_SENTINEL = "@@CYBERDECK_KEY_B64@@"


# --------------------------------------------------------------------------
# вспомогательное
# --------------------------------------------------------------------------

def b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def gen_password(length: int) -> str:
    """Крепкий пароль без неоднозначных символов и без шелл-спецсимволов."""
    alphabet = (
        "ABCDEFGHJKLMNPQRSTUVWXYZ"
        "abcdefghijkmnopqrstuvwxyz"
        "23456789"
        "-_.=+@%"
    )
    return "".join(secrets.choice(alphabet) for _ in range(max(12, length)))


def split_addr_port(token: str) -> tuple[str, int | None]:
    """'host' / 'host:port' / '[ipv6]:port' -> (host, port|None)."""
    if token.startswith("["):
        host, sep, rest = token[1:].partition("]")
        if sep and rest.startswith(":") and rest[1:].isdigit():
            return host, int(rest[1:])
        return host, None
    if token.count(":") == 1:
        host, _, port = token.partition(":")
        if port.isdigit():
            return host, int(port)
    return token, None


def parse_target(token: str, default_user: str, default_port: int) -> tuple[str, str, int]:
    """'user@host:port' -> (ssh_user, host, port), подставляя дефолты."""
    user = default_user
    if "@" in token:
        user, token = token.split("@", 1)
    host, port = split_addr_port(token)
    return user, host, port or default_port


def read_public_key(args, ui: UI) -> str | None:
    """Публичный ключ из --ssh-key или --ssh-key-file (может быть несколько строк)."""
    if args.ssh_key:
        text = args.ssh_key.strip()
    elif args.ssh_key_file:
        path = Path(args.ssh_key_file)
        if not path.is_file():
            ui.err_msg(f"файл ключа не найден: {path}")
            return None
        text = path.read_text(encoding="utf-8").strip()
    else:
        return None

    valid = [l for l in text.splitlines() if l.strip()]
    for line in valid:
        if not re.match(r"^(ssh-(rsa|ed25519|dss)|ecdsa-|sk-)", line.strip()):
            ui.warn(f"строка не похожа на публичный ключ: {line[:40]}…")
    return "\n".join(valid) if valid else None


# --------------------------------------------------------------------------
# генерация удалённого скрипта
# --------------------------------------------------------------------------

def build_remote_script(opts: dict) -> str:
    """Собрать идемпотентный bash с плейсхолдерами под секреты (см. PW/KEY_SENTINEL)."""
    q = shlex.quote
    L: list[str] = []
    add = L.append

    add("set -eu")
    add("u=" + q(opts["user"]))
    add("shell=" + q(opts["shell"]))
    if opts.get("uid"):
        add("uid=" + q(str(opts["uid"])))
    if opts.get("gecos"):
        add("gecos=" + q(opts["gecos"]))
    if opts.get("home"):
        add("home_dir=" + q(opts["home"]))
    add("")
    add('if [ "$(id -u)" -ne 0 ]; then')
    add('  echo "adduser: на сервере нужен root (заходи под root или добавь --become)" >&2; exit 11')
    add("fi")
    add("")

    # 1. пользователь
    add('if id "$u" >/dev/null 2>&1; then')
    add('  echo "exists: $u"')
    add("else")
    useradd = '  useradd -m -s "$shell"'
    if opts.get("uid"):
        useradd += ' -u "$uid"'
    if opts.get("gecos"):
        useradd += ' -c "$gecos"'
    if opts.get("home"):
        useradd += ' -d "$home_dir"'
    useradd += ' "$u"'
    add(useradd)
    add('  echo "created: $u"')
    add("fi")
    add("")

    # 2. доп. группы
    if opts.get("groups"):
        grp = ",".join(opts["groups"])
        add(f'usermod -aG {q(grp)} "$u" && echo "groups: {grp}"')

    # 3. админ (sudo/wheel)
    if opts.get("admin"):
        add('adm=""')
        add('if getent group sudo >/dev/null 2>&1; then adm=sudo; '
            'elif getent group wheel >/dev/null 2>&1; then adm=wheel; fi')
        add('if [ -n "$adm" ]; then usermod -aG "$adm" "$u"; echo "admin: +$adm"; '
            'else echo "admin: нет группы sudo/wheel" >&2; fi')

    # 4. sudo без пароля
    if opts.get("nopasswd"):
        add('sf="/etc/sudoers.d/90-cyberdeck-$u"')
        add('printf "%s ALL=(ALL) NOPASSWD:ALL\\n" "$u" > "$sf"')
        add('chmod 440 "$sf"')
        add('if visudo -cf "$sf" >/dev/null 2>&1; then echo "sudoers: NOPASSWD"; '
            'else rm -f "$sf"; echo "sudoers: невалидно, откатил" >&2; exit 12; fi')

    # 5. пароль
    if opts.get("password_b64"):
        add(f"printf '%s' '{PW_SENTINEL}' | base64 -d | chpasswd && echo 'password: set'")
    elif opts.get("lock"):
        add('passwd -l "$u" >/dev/null 2>&1 || usermod -L "$u" || true')
        add('echo "password: locked"')

    # 6. SSH-ключ
    if opts.get("key_b64"):
        add('kh="$(getent passwd "$u" | cut -d: -f6)"')
        add('[ -n "$kh" ] || { echo "sshkey: не нашёл home пользователя" >&2; exit 13; }')
        add('ug="$(id -gn "$u")"')
        add('install -d -m 700 -o "$u" -g "$ug" "$kh/.ssh"')
        add('ak="$kh/.ssh/authorized_keys"')
        add('touch "$ak"')
        add(f"keydata=\"$(printf '%s' '{KEY_SENTINEL}' | base64 -d)\"")
        add('added=0')
        add('while IFS= read -r kl; do')
        add('  [ -z "$kl" ] && continue')
        add('  if ! grep -qxF "$kl" "$ak"; then printf "%s\\n" "$kl" >> "$ak"; added=$((added+1)); fi')
        add("done <<CDK_EOF")
        add("$keydata")
        add("CDK_EOF")
        add('chmod 600 "$ak"')
        add('chown "$u":"$ug" "$ak" "$kh/.ssh"')
        add('echo "sshkey: установлено ключей +$added"')

    add("")
    add('echo "DONE: $u"')
    return "\n".join(L) + "\n"


def fill_secrets(script: str, opts: dict) -> str:
    out = script
    if opts.get("password_b64"):
        out = out.replace(PW_SENTINEL, opts["password_b64"])
    if opts.get("key_b64"):
        out = out.replace(KEY_SENTINEL, opts["key_b64"])
    return out


def masked_script(script: str, opts: dict) -> str:
    out = script.replace(PW_SENTINEL, "<PASSWORD-REDACTED>")
    if opts.get("key_b64"):  # публичный ключ прятать незачем
        out = out.replace(KEY_SENTINEL, opts["key_b64"])
    return out


# --------------------------------------------------------------------------
# запуск по SSH
# --------------------------------------------------------------------------

def ssh_command(args, ssh_user: str, host: str, port: int) -> list[str]:
    cmd = ["ssh", "-o", f"ConnectTimeout={args.timeout}"]
    if args.batch:
        cmd += ["-o", "BatchMode=yes"]
    if port != 22:
        cmd += ["-p", str(port)]
    if args.identity:
        cmd += ["-i", args.identity]
    for opt in args.ssh_option or []:
        cmd += ["-o", opt]
    cmd.append(f"{ssh_user}@{host}")
    cmd.append("sudo -n bash -s" if args.become else "bash -s")
    return cmd


def run_target(args, token: str, script: str, ui: UI, env: Envelope) -> None:
    ssh_user, host, port = parse_target(token, args.ssh_user, args.ssh_port)
    dest = f"{ssh_user}@{host}" + (f":{port}" if port != 22 else "")
    rec = env.host(host)
    rec["destination"] = dest
    rec["actions"] = []

    ui.stage(f"{dest} — завожу {args.user}")
    cmd = ssh_command(args, ssh_user, host, port)
    ui.dim(" ".join(shlex.quote(c) for c in cmd))

    try:
        proc = subprocess.run(
            cmd, input=script.encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=args.timeout + 60,
        )
    except FileNotFoundError:
        ui.err_msg("не найден бинарь ssh в PATH")
        env.fail("ssh не установлен")
        rec["state"] = "error"
        return
    except subprocess.TimeoutExpired:
        ui.err_msg(f"{dest}: таймаут соединения/выполнения")
        env.warn(f"{host}: таймаут")
        rec["state"] = "error"
        return

    out = proc.stdout.decode("utf-8", "replace")
    errtext = proc.stderr.decode("utf-8", "replace")
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        rec["actions"].append(line)
        if not line.startswith("DONE"):
            ui.ok(f"{host}: {line}")

    if proc.returncode == 0:
        rec["state"] = "ok"
        created = any(a.startswith("created:") for a in rec["actions"])
        ui.ok(f"{dest}: готово ({'создан' if created else 'уже был'})")
    else:
        rec["state"] = "error"
        env.status = "partial" if env.status == "ok" else env.status
        detail = errtext.strip().splitlines()[-1] if errtext.strip() else f"код {proc.returncode}"
        env.warn(f"{host}: {detail}")
        ui.err_msg(f"{dest}: не удалось — {detail}")
    for line in errtext.splitlines():
        if line.strip():
            ui.raw(line.strip())


# --------------------------------------------------------------------------
# отчёт
# --------------------------------------------------------------------------

def human_report(payload: dict, generated: dict) -> None:
    stats = payload["stats"]
    print("\n== MKUSER ==")
    print(f"  серверов ...... {stats.get('targets', 0)}")
    print(f"  успешно ....... {stats.get('ok', 0)}")
    print(f"  с ошибкой ..... {stats.get('failed', 0)}")
    print(f"  пользователь .. {stats.get('user', '-')}")
    print("\n  серверы:")
    for host in payload["hosts"]:
        mark = "ok" if host.get("state") == "ok" else "ERR"
        print(f"    [{mark:>3}] {host.get('destination', host['ip'])}")
        for action in host.get("actions", []):
            print(f"          {action}")
    if generated:
        print("\n  сгенерированные пароли (сохрани, больше не покажутся):")
        for user, pw in generated.items():
            print(f"    {user}: {pw}")
    print()


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adduser",
        description="Завести пользователя на сервере(ах) по SSH. Цепочки через --json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "примеры:\n"
            "  ./adduser.py root@1.2.3.4 -u deploy --ssh-key-file id.pub\n"
            "  ./adduser.py 10.0.0.5 -u ops --admin --random-password\n"
            "  ./ipscan.py hosts.txt --alive-only --json | ./adduser.py -u ci --nopasswd-sudo --ssh-key-file ci.pub\n"
            "  ./adduser.py root@host -u test --dry-run   # показать скрипт, не подключаясь\n"
        ),
    )
    parser.add_argument("targets", nargs="*", help="user@host[:port] (иначе цели со stdin)")

    conn = parser.add_argument_group("подключение")
    conn.add_argument("--ssh-user", default="root", help="логин для SSH (по умолчанию root)")
    conn.add_argument("-p", "--ssh-port", type=int, default=22, help="порт SSH (22)")
    conn.add_argument("-i", "--identity", help="приватный ключ для SSH-аутентификации")
    conn.add_argument("--ssh-option", action="append", metavar="OPT", help="доп. -o для ssh (повторяемо)")
    conn.add_argument("--become", action="store_true", help="выполнять на сервере через sudo -n (если логин не root)")
    conn.add_argument("--batch", action="store_true", help="BatchMode: не спрашивать пароль SSH (только ключи)")
    conn.add_argument("--timeout", type=int, default=15, help="таймаут соединения, сек (15)")

    usr = parser.add_argument_group("пользователь")
    usr.add_argument("-u", "--user", help="имя создаваемого пользователя (обязательно)")
    usr.add_argument("--uid", type=int, help="явный UID")
    usr.add_argument("--shell", default="/bin/bash", help="login shell (/bin/bash)")
    usr.add_argument("--gecos", help="комментарий/полное имя")
    usr.add_argument("-G", "--groups", help="доп. группы через запятую")
    usr.add_argument("--home", help="путь домашнего каталога")

    priv = parser.add_argument_group("права")
    priv.add_argument("--admin", action="store_true", help="в группу sudo/wheel (root-права)")
    priv.add_argument("--nopasswd-sudo", action="store_true", help="sudo без пароля (подразумевает --admin)")

    pw = parser.add_argument_group("пароль")
    pw.add_argument("--password", metavar="PLAIN", help="задать этот пароль (виден в ps/history локально)")
    pw.add_argument("--ask-password", action="store_true", help="спросить пароль скрытым вводом")
    pw.add_argument("--random-password", action="store_true", help="сгенерировать пароль и показать")
    pw.add_argument("--length", type=int, default=20, help="длина случайного пароля (20)")
    pw.add_argument("--lock", action="store_true", help="явно заблокировать пароль (вход только по ключу)")

    key = parser.add_argument_group("SSH-ключ")
    key.add_argument("--ssh-key", metavar="STR", help="публичный ключ строкой")
    key.add_argument("--ssh-key-file", metavar="FILE", help="файл с публичным ключом (можно несколько строк)")

    out = parser.add_argument_group("вывод")
    out.add_argument("--dry-run", action="store_true", help="показать удалённый скрипт, не подключаясь")
    out.add_argument("--json", action="store_true", help="конверт cyberdeck.v1 в stdout")
    out.add_argument("--show-secrets", action="store_true", help="включить сгенерированные пароли в JSON")
    out.add_argument("-o", "--out", help="сохранить JSON в файл")
    out.add_argument("-q", "--quiet", action="store_true", help="без логов")
    out.add_argument("-v", "--verbose", action="store_true", help="показывать stderr сервера")
    out.add_argument("--no-color", action="store_true", help="без цвета")
    return parser


def resolve_password(args, ui: UI) -> tuple[str | None, bool]:
    """(plaintext|None, is_random). Разруливает конфликт режимов."""
    chosen = [n for n, v in (
        ("--password", args.password is not None),
        ("--ask-password", args.ask_password),
        ("--random-password", args.random_password),
    ) if v]
    if len(chosen) > 1:
        ui.err_msg(f"выбери один способ пароля, а не {', '.join(chosen)}")
        raise SystemExit(2)
    if args.password is not None:
        return args.password, False
    if args.ask_password:
        return getpass.getpass("Пароль нового пользователя: "), False
    if args.random_password:
        return gen_password(args.length), True
    return None, False


def main() -> int:
    args = build_parser().parse_args()
    ui = UI(quiet=args.quiet, verbose=args.verbose, color=not args.no_color)

    if not args.user:
        ui.err_msg("не задано имя пользователя: добавь -u/--user")
        return 2
    if not RE_USERNAME.match(args.user):
        ui.err_msg(f"недопустимое имя пользователя: {args.user!r} (ожидается [a-z_][a-z0-9_-]*)")
        return 2

    env = Envelope(TOOL, VERSION, params={
        "user": args.user,
        "admin": args.admin or args.nopasswd_sudo,
        "nopasswd_sudo": args.nopasswd_sudo,
        "ssh_user": args.ssh_user,
        "become": args.become,
    })
    ui.banner("CYBERDECK :: adduser", f"run {env.run_id}")

    plaintext, is_random = resolve_password(args, ui)
    key_text = read_public_key(args, ui)
    if args.ssh_key_file and key_text is None and not args.ssh_key:
        return 2  # файл ключа указан, но не прочитан
    if plaintext is None and key_text is None and not args.lock:
        ui.warn("ни пароля, ни ключа — пользователь не сможет войти (только консоль сервера)")

    opts = {
        "user": args.user,
        "shell": args.shell,
        "uid": args.uid,
        "gecos": args.gecos,
        "home": args.home,
        "groups": [g.strip() for g in args.groups.split(",")] if args.groups else [],
        "admin": args.admin or args.nopasswd_sudo,
        "nopasswd": args.nopasswd_sudo,
        "password_b64": b64(f"{args.user}:{plaintext}") if plaintext is not None else None,
        "lock": args.lock and plaintext is None,
        "key_b64": b64(key_text) if key_text else None,
    }

    template = build_remote_script(opts)

    if args.dry_run:
        ui.info("dry-run: удалённый скрипт (пароль скрыт), подключения нет")
        print(masked_script(template, opts))
        if is_random:
            ui.ok(f"сгенерированный пароль был бы: {plaintext}")
        return 0

    # цели: аргументы или stdin (конверт/список)
    targets = list(args.targets)
    if not targets and not sys.stdin.isatty():
        piped = read_input(sys.stdin.read())
        targets += [h["ip"] for h in piped.hosts] or piped.targets
    targets = list(dict.fromkeys(targets))
    if not targets:
        ui.err_msg("нет целей: укажи user@host аргументом или подай хосты на stdin")
        return 2
    env.targets = targets

    script = fill_secrets(template, opts)
    generated: dict[str, str] = {}
    if is_random:
        generated[args.user] = plaintext  # покажем в отчёте/логе
        ui.ok(f"пароль для {args.user}: {plaintext}  (сохрани — больше не покажу)")

    for token in targets:
        run_target(args, token, script, ui, env)

    ok = sum(1 for h in env.hosts if h.get("state") == "ok")
    failed = len(env.hosts) - ok
    if failed and ok:
        env.status = "partial"
    elif failed and not ok:
        env.status = "error"
    env.add_stat("user", args.user)
    env.add_stat("ok", ok)
    env.add_stat("failed", failed)

    payload = env.to_dict()
    if args.show_secrets and generated:
        for host in payload["hosts"]:
            if host.get("state") == "ok":
                host.setdefault("user", {})["generated_password"] = generated.get(args.user)

    if args.out:
        import json
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        ui.ok(f"JSON сохранён: {args.out}")

    if args.json:
        import json
        print(json.dumps(payload, ensure_ascii=False, indent=None if args.quiet else 2))
    else:
        human_report(payload, generated)

    return 0 if env.status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
