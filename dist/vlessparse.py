#!/usr/bin/env python3
"""vlessparse — разбор ссылок VLESS (и соседних схем) в конверт cyberdeck.v1.

Сеть не трогает: только парсинг. Каждый конфиг — это эндпоинт ``host:port``,
поэтому сервер уходит в ``hosts`` конверта, а весь разбор (uuid, sni, security,
type, flow, pbk/sid, remark) складывается в ``host["configs"]`` без потери
дублей на одном адресе. Дальше цепочка сама решает, что с адресами делать:

    cat sub.txt | ./vlessparse.py --json | ./ipscan.py --geo --json
    cat sub.txt | ./vlessparse.py --targets | sudo ./portscan.py --json

Разбор через ``urllib.urlsplit`` (а не regex по ``@host:``): берётся настоящий
порт, IPv6 в скобках, домены и все query-параметры. Кроме ``vless://`` понимает
``trojan://``, ``vmess://`` (base64-JSON) и ``ss://`` (SIP002) — по возможности.

Логи и прогресс — в stderr, JSON (--json) или человекочитаемый отчёт — в stdout.
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
import binascii
import json
import sys
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit


from cyberdeck import Envelope, make_port  # noqa: E402
from cyberdeck.ui import UI, force_utf8  # noqa: E402

force_utf8()

TOOL = "vlessparse"
VERSION = "0.1.0"

# Схемы с формой userinfo@host:port?query#remark — разбираются одинаково.
_USERINFO_SCHEMES = {"vless", "trojan"}
SUPPORTED = _USERINFO_SCHEMES | {"vmess", "ss"}

# Известные ключи прокси-конфига — их вытаскиваем в предсказуемом виде, остальные
# query-параметры тоже сохраняем как есть (universal: ничего не теряем).
_KNOWN_KEYS = (
    "security", "encryption", "type", "flow", "sni", "fp", "pbk", "sid", "spx",
    "host", "path", "serviceName", "mode", "alpn", "headerType", "extra",
)


def _b64decode(data: str) -> bytes:
    """Терпимый base64/base64url: чинит паддинг, пробует оба алфавита."""
    data = data.strip().replace("\n", "")
    pad = "=" * (-len(data) % 4)
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            return decoder(data + pad)
        except (binascii.Error, ValueError):
            continue
    raise ValueError("не base64")


def _clean(cfg: dict) -> dict:
    """Выбросить пустые поля — конверт должен читаться."""
    return {k: v for k, v in cfg.items() if v not in (None, "", [], {})}


def parse_userinfo(scheme: str, line: str) -> dict:
    """vless:// и trojan:// — общая форма userinfo@host:port?query#remark."""
    parts = urlsplit(line)
    if not parts.hostname:
        raise ValueError("нет адреса хоста")
    if parts.port is None:  # .port сам бросит ValueError на мусоре
        raise ValueError("нет порта")

    query = dict(parse_qsl(parts.query, keep_blank_values=False))
    cfg = {
        "scheme": scheme,
        "address": parts.hostname,
        "port": parts.port,
        "id": unquote(parts.username or ""),
        "remark": unquote(parts.fragment),
    }
    for key in _KNOWN_KEYS:
        if key in query:
            cfg[key] = query.pop(key)
    cfg.update(query)  # всё нераспознанное — тоже в конфиг, не теряем
    cfg["raw"] = line
    return _clean(cfg)


def parse_vmess(line: str) -> dict:
    """vmess:// — base64 от JSON {add, port, id, net, tls, sni, ps, ...}."""
    payload = json.loads(_b64decode(line[len("vmess://"):]))
    if not isinstance(payload, dict):
        raise ValueError("vmess: не JSON-объект")
    port = payload.get("port")
    if port in (None, ""):
        raise ValueError("нет порта")
    cfg = {
        "scheme": "vmess",
        "address": str(payload.get("add", "")).strip(),
        "port": int(port),
        "id": str(payload.get("id", "")),
        "type": payload.get("net", ""),
        "security": payload.get("tls", ""),
        "sni": payload.get("sni") or payload.get("host", ""),
        "path": payload.get("path", ""),
        "host": payload.get("host", ""),
        "alpn": payload.get("alpn", ""),
        "aid": payload.get("aid", ""),
        "remark": payload.get("ps", ""),
        "raw": line,
    }
    if not cfg["address"]:
        raise ValueError("нет адреса хоста")
    return _clean(cfg)


def parse_ss(line: str) -> dict:
    """ss:// — SIP002 (base64(method:pass)@host:port) и цельно-base64 форма."""
    body, _, fragment = line[len("ss://"):].partition("#")
    remark = unquote(fragment)

    if "@" not in body:  # ss://base64(method:pass@host:port)
        body = _b64decode(body.split("?", 1)[0]).decode("utf-8", "replace")

    userinfo, _, hostport = body.partition("@")
    if not hostport:
        raise ValueError("ss: не разобрал host:port")

    if ":" not in userinfo:  # userinfo мог быть base64(method:pass)
        try:
            userinfo = _b64decode(userinfo).decode("utf-8", "replace")
        except ValueError:
            pass
    method, _, password = userinfo.partition(":")

    hostport = hostport.split("?", 1)[0].split("/", 1)[0]
    parts = urlsplit(f"//{hostport}")
    if not parts.hostname or parts.port is None:
        raise ValueError("ss: нет host:port")

    return _clean({
        "scheme": "ss",
        "address": parts.hostname,
        "port": parts.port,
        "method": method,
        "id": password,
        "remark": remark,
        "raw": line,
    })


def parse_line(line: str) -> dict:
    scheme = line.split("://", 1)[0].lower()
    if scheme in _USERINFO_SCHEMES:
        return parse_userinfo(scheme, line)
    if scheme == "vmess":
        return parse_vmess(line)
    if scheme == "ss":
        return parse_ss(line)
    raise ValueError(f"схема не поддержана: {scheme}")


def iter_links(text: str):
    """Строки-ссылки из текста. Пустое, комментарии (# / //) — мимо."""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue
        yield line


# --------------------------------------------------------------------------
# сбор ввода
# --------------------------------------------------------------------------

def gather_text(args, ui: UI) -> str:
    """Ввод из файлов-аргументов, прямых ссылок в аргументах или из stdin."""
    chunks: list[str] = []
    literal = 0
    for token in args.inputs:
        path = Path(token)
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
        elif "://" in token:
            chunks.append(token)
            literal += 1
        else:
            ui.warn(f"пропущено (не файл и не ссылка): {token}")
    if literal:
        ui.info(f"ссылок из аргументов: {literal}")

    if not chunks and not sys.stdin.isatty():
        chunks.append(sys.stdin.read())

    return "\n".join(chunks)


# --------------------------------------------------------------------------
# отчёт
# --------------------------------------------------------------------------

def human_report(payload: dict) -> None:
    """Человекочитаемая сводка в stdout (когда без --json)."""
    stats = payload["stats"]
    hosts = payload["hosts"]

    print("\n== VLESS PARSE ==")
    print(f"  строк на входе .... {stats.get('lines_in', 0)}")
    print(f"  конфигов .......... {stats.get('configs', 0)}")
    print(f"  не разобрано ...... {stats.get('failed', 0)}")
    print(f"  уникальных хостов . {len(hosts)}")
    print(f"  эндпоинтов host:port {stats.get('endpoints', 0)}")

    by_scheme = stats.get("by_scheme", {})
    if by_scheme:
        print("\n  по схемам:")
        for name, count in sorted(by_scheme.items(), key=lambda kv: -kv[1]):
            print(f"    {name:<8} {count}")

    by_security = stats.get("by_security", {})
    if by_security:
        print("\n  по security:")
        for name, count in sorted(by_security.items(), key=lambda kv: -kv[1]):
            print(f"    {name or '(нет)':<12} {count}")

    print("\n  хосты:")
    for host in hosts:
        ports = ",".join(str(p["port"]) for p in host["ports"])
        remarks = [c.get("remark", "") for c in host.get("configs", []) if c.get("remark")]
        tag = f"  {remarks[0]}" if remarks else ""
        extra = f" (+{len(remarks) - 1})" if len(remarks) > 1 else ""
        print(f"    {host['ip']:<22} :{ports:<16} [{len(host.get('configs', []))} cfg]{tag}{extra}")
    print()


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vlessparse",
        description="Разбор VLESS/trojan/vmess/ss в конверт cyberdeck.v1. Цепочки через --json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "примеры:\n"
            "  cat sub.txt | ./vlessparse.py\n"
            "  ./vlessparse.py sub.txt --json | ./ipscan.py --geo --json\n"
            "  cat sub.txt | ./vlessparse.py --targets | sudo ./portscan.py --json\n"
        ),
    )
    parser.add_argument("inputs", nargs="*", help="файлы с ссылками или сами ссылки (иначе stdin)")

    flt = parser.add_argument_group("фильтры")
    flt.add_argument("--scheme", action="append", metavar="NAME",
                     help="оставить только эти схемы (можно повторять): vless/trojan/vmess/ss")
    flt.add_argument("--unique", action="store_true",
                     help="схлопнуть эндпоинты host:port до уникальных (по одному конфигу)")

    out = parser.add_argument_group("вывод")
    out.add_argument("--json", action="store_true", help="конверт cyberdeck.v1 в stdout")
    out.add_argument("--targets", action="store_true",
                     help="печатать только уникальные адреса host:port построчно (для пайпа)")
    out.add_argument("-o", "--out", help="сохранить JSON в файл")
    out.add_argument("-q", "--quiet", action="store_true", help="без логов")
    out.add_argument("-v", "--verbose", action="store_true", help="показывать причины отбраковки")
    out.add_argument("--no-color", action="store_true", help="без цвета")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    ui = UI(quiet=args.quiet, verbose=args.verbose, color=not args.no_color)

    scheme_filter = {s.lower() for s in args.scheme} if args.scheme else None
    env = Envelope(TOOL, VERSION, params={
        "schemes": sorted(scheme_filter) if scheme_filter else "all",
        "unique": args.unique,
    })
    ui.banner("CYBERDECK :: vlessparse", f"run {env.run_id}")

    text = gather_text(args, ui)
    if not text.strip():
        ui.err_msg("нет ввода: подай ссылки на stdin, файлом или аргументом")
        return 2

    lines_in = 0
    configs = 0
    failed = 0
    by_scheme: dict[str, int] = {}
    by_security: dict[str, int] = {}
    seen_endpoints: set[tuple[str, int]] = set()

    for line in iter_links(text):
        lines_in += 1
        try:
            cfg = parse_line(line)
        except ValueError as exc:
            failed += 1
            ui.raw(f"skip: {exc} :: {line[:60]}")
            continue
        except Exception as exc:  # noqa: BLE001 — не роняем разбор из-за одной битой строки
            failed += 1
            ui.raw(f"skip: {type(exc).__name__}: {exc} :: {line[:60]}")
            continue

        if scheme_filter and cfg["scheme"] not in scheme_filter:
            continue

        addr, port = cfg["address"], cfg["port"]
        endpoint = (addr, port)
        if args.unique and endpoint in seen_endpoints:
            continue
        seen_endpoints.add(endpoint)

        env.host(addr)["state"] = "unknown"
        env.add_port(addr, make_port(port, "tcp", "unknown", source=cfg["scheme"], service=cfg["scheme"]))
        env.host(addr).setdefault("configs", []).append(cfg)

        configs += 1
        by_scheme[cfg["scheme"]] = by_scheme.get(cfg["scheme"], 0) + 1
        sec = cfg.get("security", "")
        by_security[sec] = by_security.get(sec, 0) + 1

    env.targets = [h["ip"] for h in env.hosts]
    if failed:
        env.warn(f"не разобрано строк: {failed}")
        if configs == 0:
            env.status = "error"

    env.add_stat("lines_in", lines_in)
    env.add_stat("configs", configs)
    env.add_stat("failed", failed)
    env.add_stat("endpoints", len(seen_endpoints))
    env.add_stat("by_scheme", by_scheme)
    env.add_stat("by_security", by_security)

    payload = env.to_dict()
    ui.ok(f"разобрано конфигов: {configs}, хостов: {len(payload['hosts'])}, отбраковано: {failed}")

    if args.out:
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        ui.ok(f"JSON сохранён: {args.out}")

    if args.targets:
        for addr, port in sorted(seen_endpoints):
            print(f"{addr}:{port}")
    elif args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=None if args.quiet else 2))
    else:
        human_report(payload)

    return 0 if env.status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
