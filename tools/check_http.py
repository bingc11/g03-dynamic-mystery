"""Exercise the running local demo. Streams use the local fixture launched by local_demo.py."""
import argparse
import json
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=10000)
    base = "http://127.0.0.1:" + str(parser.parse_args().port)

    def request(path, body=None, key=None):
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        req = urllib.request.Request(base + path, headers=headers,
            data=None if body is None else json.dumps(body).encode())
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read().decode()

    demo = json.loads(request("/npc/runs", {"case":"example_4"}))
    key = demo["run"]
    def act(version, action, actor, source, token=key):
        return json.loads(request("/npc/act", dict(version=version, action=action, actor=actor, source=source), token))

    first = act(0, "ask", "御史大夫", "registry")
    assert "没有收到" in first["reply"]
    shown = act(1, "show", "太平公主", "evidence_manuscript_missing")
    assert "御史" not in str(shown)
    assert "可以再问" in act(2, "ask", "御史大夫", "registry")["reply"]
    assert "太平公主" in act(3, "ask", "御史大夫", "registry_origin")["reply"]
    for token, version, expected in [(key, 0, 409), ("invalid", 4, 404)]:
        try:
            act(version, "ask", "御史大夫", "registry", token)
        except urllib.error.HTTPError as exc:
            assert exc.code == expected
        else:
            raise AssertionError("invalid request accepted")
    fresh = json.loads(request("/npc/runs", {"case":"example_4"}))
    assert "没有收到" in act(0, "ask", "御史大夫", "registry", fresh["run"])["reply"]
    print("PASS: separate runs, three recipients, private action, sourced follow-up, stale and invalid requests")


if __name__ == "__main__":
    main()
