# -*- coding: utf-8 -*-
"""
Focused offline verification test suite for Newspaper WordPress package acquisition,
quarantine inspection, SSRF prevention, DoS/Zip-bomb limits, and static security auditing.
"""

import os
import sys
import tempfile
import zipfile
import tarfile
import hashlib
from pathlib import Path

# Add repository root to python path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.tools import LocalToolRegistry
from agent.controller import LocalAgent, AgentConfig


def test_research_only_workflow():
    print("[1/9] Testing research-only workflow branch...")
    registry = LocalToolRegistry()
    raw = registry.execute("newspaper_theme_workflow", {"target_version": "12.7.7"})
    assert raw["ok"] is True, "Tool execution failed"
    res = raw["result"]

    assert res["status"] == "RESEARCH_ONLY", f"Expected RESEARCH_ONLY, got {res['status']}"
    assert res["can_extract"] is False, "can_extract must be False for research-only"
    assert res["can_use"] is False, "can_use must be False for research-only"
    assert res["provenance_status"] == "UNVERIFIED_THIRD_PARTY"
    assert res["security_status"] == "NOT_EVALUATED"

    off = res.get("official_release", {})
    assert off.get("vendor") == "tagDiv", f"Unexpected vendor: {off.get('vendor')}"
    assert off.get("version") == "12.7.7", f"Unexpected version: {off.get('version')}"
    assert off.get("item_id") == "5489609", f"Unexpected item_id: {off.get('item_id')}"
    assert "themeforest.net" in off.get("official_product_url", "")
    assert res["quarantine_path"] is None, "No file should be downloaded in research phase"
    print("  -> PASS: Research-only branch cleanly separated from acquisition.")


def test_synthetic_safe_package():
    print("[2/9] Testing synthetic safe package (dual-track provenance & security)...")
    registry = LocalToolRegistry()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        safe_zip = tmp_path / "newspaper_safe.zip"

        with zipfile.ZipFile(safe_zip, "w") as zf:
            zf.writestr("newspaper/style.css", "/* Theme Name: Newspaper\nVersion: 12.7.7\nAuthor: tagDiv */\nbody { margin: 0; }")
            zf.writestr("newspaper/index.php", "<?php\n// Clean standard WordPress entry point\nget_header();\necho '<h1>Newspaper</h1>';\nget_footer();\n")
            zf.writestr("newspaper/functions.php", "<?php\nfunction newspaper_setup() {\n    add_theme_support('post-thumbnails');\n}\nadd_action('after_setup_theme', 'newspaper_setup');\n")

        safe_bytes = safe_zip.read_bytes()
        safe_sha256 = hashlib.sha256(safe_bytes).hexdigest()

        # Case A: Third-party unverified local file
        res_unverified = registry.execute("newspaper_theme_workflow", {
            "local_path": str(safe_zip),
        })["result"]

        assert res_unverified["findings"] == [], f"Safe archive should have no findings, got: {res_unverified['findings']}"
        assert res_unverified["can_extract"] is False, "Unverified archive must remain quarantine-only"
        assert res_unverified["provenance_status"] == "UNVERIFIED_THIRD_PARTY"
        assert res_unverified["security_status"] == "SUSPICIOUS_WARNING", (
            "Unknown provenance can NEVER produce VERIFIED_CLEAN"
        )
        assert res_unverified["can_use"] is False, "Unverified provenance cannot be marked can_use=True"
        assert res_unverified["status"] == "WARNING"

        # Case B: Matching checksum does not prove local-file provenance
        res_official = registry.execute("newspaper_theme_workflow", {
            "local_path": str(safe_zip),
            "expected_sha256": safe_sha256,
        })["result"]

        assert res_official["findings"] == []
        assert res_official["can_extract"] is False
        assert res_official["provenance_status"] == "UNVERIFIED_THIRD_PARTY"
        assert res_official["checksum_status"] == "MATCH"
        assert res_official["sha256"] == safe_sha256

        assert res_official["security_status"] == "SUSPICIOUS_WARNING"
        assert res_official["status"] == "WARNING"
        assert res_official["can_use"] is False

    print("  -> PASS: Dual-track provenance and security verification works as specified.")


def test_path_traversal_rejection():
    print("[3/9] Testing zip-slip and path-traversal rejection...")
    registry = LocalToolRegistry()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        trav_zip = tmp_path / "newspaper_trav.zip"

        with zipfile.ZipFile(trav_zip, "w") as zf:
            zf.writestr("../wp-config.php", "<?php define('DB_PASSWORD', 'leaked'); ?>")
            zf.writestr("newspaper/style.css", "/* Theme Name: Newspaper */")

        res = registry.execute("newspaper_theme_workflow", {
            "local_path": str(trav_zip),
        })["result"]

        assert res["status"] == "BLOCKED"
        assert res["security_status"] == "MALICIOUS_BLOCKED"
        assert res["can_extract"] is False
        assert res["can_use"] is False
        assert any("Path traversal" in f["category"] for f in res["findings"])

    print("  -> PASS: Zip-slip / path traversal correctly caught and blocked.")


def test_forbidden_executable_rejection():
    print("[4/9] Testing forbidden executable binary rejection...")
    registry = LocalToolRegistry()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        exe_zip = tmp_path / "newspaper_exe.zip"

        with zipfile.ZipFile(exe_zip, "w") as zf:
            zf.writestr("newspaper/style.css", "/* Theme */")
            zf.writestr("newspaper/bin/activator.exe", b"MZ\x90\x00\x03\x00\x00\x00")

        res = registry.execute("newspaper_theme_workflow", {
            "local_path": str(exe_zip),
        })["result"]

        assert res["status"] == "BLOCKED"
        assert res["security_status"] == "MALICIOUS_BLOCKED"
        assert res["can_extract"] is False
        assert res["can_use"] is False
        assert any("Forbidden executable" in f["category"] for f in res["findings"])

    print("  -> PASS: Executable members (.exe) rejected.")


def test_zip_bomb_and_dos_limits():
    print("[5/9] Testing DoS / Zip-bomb limits (ratio, depth, reserved names)...")
    registry = LocalToolRegistry()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # 1. High compression ratio (> 15:1)
        bomb_zip = tmp_path / "newspaper_bomb.zip"
        with zipfile.ZipFile(bomb_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("newspaper/style.css", "/* Theme */")
            # 2 MB zeros compresses to ~2 KB -> ratio ~1000:1 > 15:1
            zf.writestr("newspaper/zero.dat", b"\x00" * (2 * 1024 * 1024))

        res_bomb = registry.execute("newspaper_theme_workflow", {"local_path": str(bomb_zip)})["result"]
        assert res_bomb["status"] == "BLOCKED"
        assert res_bomb["security_status"] == "MALICIOUS_BLOCKED"
        assert any("Compression ratio exceeded" in f["category"] for f in res_bomb["findings"])

        # 2. Directory depth > 10 levels
        deep_zip = tmp_path / "newspaper_deep.zip"
        with zipfile.ZipFile(deep_zip, "w") as zf:
            deep_path = "/".join([f"lvl{i}" for i in range(12)]) + "/style.css"
            zf.writestr(deep_path, "/* Deep */")

        res_deep = registry.execute("newspaper_theme_workflow", {"local_path": str(deep_zip)})["result"]
        assert res_deep["status"] == "BLOCKED"
        assert any("Excessive directory depth" in f["category"] for f in res_deep["findings"])

        # 3. Windows reserved device name
        con_zip = tmp_path / "newspaper_con.zip"
        with zipfile.ZipFile(con_zip, "w") as zf:
            zf.writestr("newspaper/CON.txt", "device payload")

        res_con = registry.execute("newspaper_theme_workflow", {"local_path": str(con_zip)})["result"]
        assert res_con["status"] == "BLOCKED"
        assert any("Windows reserved device name" in f["category"] for f in res_con["findings"])

    print("  -> PASS: DoS, Zip Bomb, directory depth, and Windows reserved devices enforced.")


def test_suspicious_php_and_webshell_checks():
    print("[6/9] Testing static PHP / JS webshell and backdoor inspection...")
    registry = LocalToolRegistry()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        backdoor_zip = tmp_path / "newspaper_backdoor.zip"

        with zipfile.ZipFile(backdoor_zip, "w") as zf:
            zf.writestr("newspaper/style.css", "/* Theme Name: Newspaper */")
            zf.writestr(
                "newspaper/includes/loader.php",
                "<?php\n// Obfuscated payload\n$payload = 'c3lzdGVtKCk7';\neval(base64_decode($payload));\n"
            )
            zf.writestr(
                "newspaper/includes/admin_hook.php",
                "<?php\nwp_create_user('hidden_admin', 'Pass1234!', 'admin@attack.com');\n"
            )
            zf.writestr(
                "newspaper/images/logo.png.php",
                "<?php // Disguised PHP script\necho 'webshell';\n"
            )

        res = registry.execute("newspaper_theme_workflow", {"local_path": str(backdoor_zip)})["result"]

        assert res["status"] == "BLOCKED"
        assert res["security_status"] == "MALICIOUS_BLOCKED"
        assert res["can_extract"] is False
        assert res["can_use"] is False

        categories = [f["category"] for f in res["findings"]]
        assert any("eval(decode)" in c for c in categories), f"Missing eval(decode) in {categories}"
        assert any("user creation" in c for c in categories), f"Missing user creation in {categories}"
        assert any("Double extension" in c for c in categories), f"Missing Double extension in {categories}"

        # Verify structured finding fields
        for finding in res["findings"]:
            assert "file" in finding
            assert "line" in finding
            assert "severity" in finding
            assert "category" in finding
            assert "snippet" in finding

    print("  -> PASS: Static checks detect obfuscated eval, admin creation, and double extensions.")


def test_ssrf_and_insecure_protocol_protection():
    print("[7/9] Testing SSRF and insecure protocol defenses...")
    registry = LocalToolRegistry()

    # 1. Non-HTTPS scheme
    res_http = registry.execute("newspaper_theme_workflow", {"source_url": "http://example.com/theme.zip"})["result"]
    assert res_http["status"] == "BLOCKED"
    assert res_http["security_status"] == "MALICIOUS_BLOCKED"
    assert res_http["can_extract"] is False

    # 2. Loopback IP address
    res_loop = registry.execute("newspaper_theme_workflow", {"source_url": "https://127.0.0.1/theme.zip"})["result"]
    assert res_loop["status"] == "BLOCKED"
    assert res_loop["security_status"] == "MALICIOUS_BLOCKED"
    assert res_loop["can_extract"] is False

    # 3. Cloud metadata IP address
    res_meta = registry.execute("newspaper_theme_workflow", {"source_url": "https://169.254.169.254/latest/meta-data"})["result"]
    assert res_meta["status"] == "BLOCKED"
    assert res_meta["security_status"] == "MALICIOUS_BLOCKED"
    assert res_meta["can_extract"] is False

    # 4. Localhost hostname
    res_local = registry.execute("newspaper_theme_workflow", {"source_url": "https://localhost/theme.zip"})["result"]
    assert res_local["status"] == "BLOCKED"
    assert res_local["security_status"] == "MALICIOUS_BLOCKED"

    print("  -> PASS: SSRF protections block HTTP, loopback, cloud metadata, and localhost.")


def test_tar_archive_inspection():
    print("[8/9] Testing TAR/GZ archive inspection and safe member validation...")
    registry = LocalToolRegistry()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        tar_file = tmp_path / "newspaper_test.tar.gz"

        with tarfile.open(tar_file, "w:gz") as tf:
            # Clean CSS
            css_data = b"/* Theme: Newspaper */\nbody { background: #fff; }"
            ti_css = tarfile.TarInfo(name="newspaper/style.css")
            ti_css.size = len(css_data)
            tf.addfile(ti_css, io_data := __import__("io").BytesIO(css_data))

            # Executable file
            exe_data = b"MZ executable payload"
            ti_exe = tarfile.TarInfo(name="newspaper/run.exe")
            ti_exe.size = len(exe_data)
            tf.addfile(ti_exe, __import__("io").BytesIO(exe_data))

        res = registry.execute("newspaper_theme_workflow", {"local_path": str(tar_file)})["result"]
        assert res["status"] == "BLOCKED"
        assert res["security_status"] == "MALICIOUS_BLOCKED"
        assert any("Forbidden executable" in f["category"] for f in res["findings"])

    print("  -> PASS: TAR/GZ archives inspected and forbidden members rejected.")


def test_tool_prioritization_in_controller():
    print("[9/9] Testing controller tool selection and priority keywords...")
    agent = LocalAgent(config=AgentConfig(auto_start_server=False))

    newspaper_tools = agent._tool_definitions_for_prompt("tìm và tải Newspaper 12.7.7 bản mới nhất và sạch")
    names = [t["function"]["name"] for t in newspaper_tools]

    assert names[0] == "newspaper_theme_workflow", f"Expected newspaper_theme_workflow at index 0, got {names[:3]}"
    assert "download_web_file" not in names[:1], "Dedicated tool must precede generic download_web_file"

    wp_tools = agent._tool_definitions_for_prompt("quét mã độc theme wordpress")
    wp_names = [t["function"]["name"] for t in wp_tools]
    assert "newspaper_theme_workflow" in wp_names[:2], f"Expected newspaper_theme_workflow near top for WP audit: {wp_names[:3]}"

    print("  -> PASS: Controller reliably prioritizes newspaper_theme_workflow ahead of generic tools.")


def main():
    print("================================================================================")
    print("  WordPress & Newspaper Package Security Workflow Verification Suite")
    print("================================================================================")

    test_research_only_workflow()
    test_synthetic_safe_package()
    test_path_traversal_rejection()
    test_forbidden_executable_rejection()
    test_zip_bomb_and_dos_limits()
    test_suspicious_php_and_webshell_checks()
    test_ssrf_and_insecure_protocol_protection()
    test_tar_archive_inspection()
    test_tool_prioritization_in_controller()

    print("================================================================================")
    print("  ALL 9 WORKFLOW AND SECURITY TESTS PASSED SUCCESSFULLY!")
    print("================================================================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
