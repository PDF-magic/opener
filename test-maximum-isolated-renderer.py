#!/usr/bin/env python3
"""Real PDF rasterization and isolation regressions for opener-0314."""

from dataclasses import FrozenInstanceError
import errno
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pymupdf

import maximum_isolated_renderer as renderer


ROOT = Path(__file__).resolve().parent


def sample_pdf(*, oversized_page=False):
    document = pymupdf.open()
    for i in range(2):
        page = document.new_page(
            width=(4096 if oversized_page else 200), height=150,
        )
        if i == 0:
            page.draw_rect(pymupdf.Rect(15, 15, 95, 95),
                           color=(1, 0, 0), fill=(1, 0, 0))
        else:
            page.draw_rect(pymupdf.Rect(30, 30, 120, 120),
                           color=(0, 0, 1), fill=(0, 0, 1))
    body = document.tobytes(garbage=3, deflate=True)
    document.close()
    return body


def frame(png, **changes):
    metadata = {
        "version": 1, "pageIndex": 0, "pageCount": 2,
        "width": 200, "height": 150, "workerPid": 123,
        "permitsOpen": False,
    }
    metadata.update(changes)
    data = json.dumps(metadata, separators=(",", ":")).encode()
    return struct.pack(">8sII", renderer.MAGIC, len(data), len(png)) + data + png


def filesystem_sandbox_command(worker, *arguments):
    context = renderer._renderer_sandbox_context(worker)
    command = [renderer.SANDBOX_EXEC, "-p", renderer.RENDERER_FILESYSTEM_PROFILE]
    for name, key in (
        ("PYTHON", "python"),
        ("WORKER", "worker"),
        ("WORKER_SUPPORT", "worker_support"),
        ("NETWORK_SUPPORT", "network_support"),
        ("RENDERER_SUPPORT", "renderer_support"),
        ("PYTHON_PREFIX", "python_prefix"),
        ("PYTHON_BASE_PREFIX", "python_base_prefix"),
    ):
        command.extend(("-D", name + "=" + context[key]))
    command.extend((context["python"], "-I", "-B", context["worker"], *arguments))
    return command


class MaximumRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pdf = sample_pdf()

    @unittest.skipUnless(sys.platform == "darwin", "Requires macOS filesystem confinement")
    def test_real_page_rasterization_uses_separate_process(self):
        render = renderer.render_isolated_pdf_page(self.pdf, 0)
        self.assertNotEqual(render.worker_pid, os.getpid())
        self.assertGreater(render.worker_pid, 0)
        self.assertEqual((render.page_index, render.page_count), (0, 2))
        self.assertEqual((render.width, render.height), (200, 150))
        self.assertTrue(render.png_bytes.startswith(renderer.PNG_SIGNATURE))
        self.assertLessEqual(len(render.png_bytes), renderer.MAX_PNG_BYTES)
        self.assertFalse(render.permits_open)
        # Decoding via an independent trusted image parser confirms actual PNG
        # content and the rendered page's expected colored rectangle.
        pix = pymupdf.Pixmap(render.png_bytes)
        self.assertEqual((pix.width, pix.height), (200, 150))
        self.assertNotEqual(pix.pixel(25, 25), pix.pixel(190, 140))

    @unittest.skipUnless(sys.platform == "darwin", "Requires macOS filesystem confinement")
    def test_two_pages_are_different_and_each_runs_in_separate_child(self):
        results = renderer.render_isolated_pdf_pages(self.pdf, (1, 0))
        self.assertEqual(tuple(x.page_index for x in results), (1, 0))
        self.assertEqual(len({x.worker_pid for x in results}), 2)
        self.assertNotEqual(results[0].png_bytes, results[1].png_bytes)
        self.assertTrue(all(x.permits_open is False for x in results))

    @unittest.skipUnless(sys.platform == "darwin", "Requires macOS filesystem confinement")
    def test_large_page_is_downscaled_before_rasterization(self):
        render = renderer.render_isolated_pdf_page(sample_pdf(oversized_page=True), 0)
        self.assertLessEqual(render.width, renderer.MAX_RENDER_SIDE)
        self.assertLessEqual(render.height, renderer.MAX_RENDER_SIDE)
        self.assertLessEqual(render.width * render.height, renderer.MAX_RENDER_PIXELS)

    def test_rejects_untrusted_inputs_without_starting_child(self):
        invalid = (
            ("not bytes", 0),
            (bytearray(self.pdf), 0),
            (b"", 0),
            (b"!" * (renderer.MAX_PDF_BYTES + 1), 0),
            (self.pdf, True),
            (self.pdf, -1),
            (self.pdf, renderer.MAX_DOCUMENT_PAGES),
            (self.pdf, "0"),
            (self.pdf, 1.0),
        )
        with patch.object(renderer.subprocess, "run") as run:
            for body, index in invalid:
                with self.subTest(index=index, size=len(body)), self.assertRaises(
                    renderer.MaximumPDFRenderError
                ):
                    renderer.render_isolated_pdf_page(body, index)
            run.assert_not_called()

    def test_batch_bounds_and_duplicates_fail_before_starting_child(self):
        invalid = (
            [], (), (0, 0), tuple(range(renderer.MAX_REQUEST_PAGES + 1)),
            (True,), (0, 512), ("1",), (0, 1, 1),
        )
        with patch.object(renderer.subprocess, "run") as run:
            for pages in invalid:
                with self.subTest(pages=pages), self.assertRaises(
                    renderer.MaximumPDFRenderError
                ):
                    renderer.render_isolated_pdf_pages(self.pdf, pages)
            run.assert_not_called()


    def test_macos_renderer_is_started_under_deny_by_default_filesystem_profile(self):
        document = pymupdf.open(stream=self.pdf, filetype="pdf")
        try:
            png = document[0].get_pixmap(
                colorspace=pymupdf.csRGB, alpha=False, annots=False,
            ).tobytes("png")
        finally:
            document.close()
        context = {
            "python": str(Path(sys.executable).resolve()),
            "worker": str((ROOT / "maximum_render_worker.py").resolve()),
            "worker_support": str((ROOT / "maximum_isolated_worker.py").resolve()),
            "network_support": str((ROOT / "maximum_network_isolation.py").resolve()),
            "renderer_support": str((ROOT / "maximum_isolated_renderer.py").resolve()),
            "python_prefix": str(Path(sys.prefix).resolve()),
            "python_base_prefix": str(Path(sys.base_prefix).resolve()),
        }
        with (
            patch.object(renderer.sys, "platform", "darwin"),
            patch.object(renderer, "_renderer_sandbox_context", return_value=context),
            patch.object(renderer.subprocess, "run", return_value=(
                subprocess.CompletedProcess([], 0, frame(png))
            )) as run,
        ):
            result = renderer.render_isolated_pdf_page(self.pdf, 0)
        command = tuple(run.call_args.args[0])
        self.assertEqual(command[:3], (
            renderer.SANDBOX_EXEC, "-p", renderer.RENDERER_FILESYSTEM_PROFILE,
        ))
        self.assertIn("(deny default)", command[2])
        self.assertIn("(deny network*)", command[2])
        self.assertIn("(deny process-fork)", command[2])
        self.assertIn('(literal (param "WORKER_SUPPORT"))', command[2])
        self.assertNotIn('(subpath (param "WORKER_DIR"))', command[2])
        self.assertNotIn("(allow file-write", command[2])
        python_index = command.index(context["python"])
        self.assertEqual(command[python_index:python_index + 3],
                         (context["python"], "-I", "-B"))
        self.assertEqual(command[-2:], (context["worker"], "0"))
        self.assertEqual(command.count("-D"), 7)
        self.assertFalse(result.permits_open)

    @unittest.skipUnless(sys.platform == "linux", "Linux seccomp enforcement test")
    def test_linux_kernel_filter_denies_socket_connect_bind_and_listen(self):
        script = "\n".join((
            "import errno, socket, sys",
            "sys.path.insert(0, sys.argv[1])",
            "outbound = socket.socket(socket.AF_INET, socket.SOCK_STREAM)",
            "bound = socket.socket(socket.AF_INET, socket.SOCK_STREAM)",
            "from maximum_network_isolation import apply_linux_network_denial",
            "apply_linux_network_denial()",
            "def denied(action):",
            "    try:",
            "        action()",
            "    except OSError as error:",
            "        return error.errno in (errno.EPERM, errno.EACCES)",
            "    return False",
            "port = int(sys.argv[2])",
            "checks = (",
            "    denied(lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM)),",
            "    denied(lambda: outbound.connect(('127.0.0.1', port))),",
            "    denied(lambda: bound.bind(('127.0.0.1', 0))),",
            "    denied(lambda: bound.listen(1)),",
            ")",
            "sys.exit(0 if all(checks) else 17)",
        ))
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            completed = subprocess.run(
                (sys.executable, "-I", "-B", "-c", script, str(ROOT), str(port)),
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, timeout=10, check=False,
                close_fds=True, cwd="/",
                env={
                    "PATH": "/usr/bin:/bin",
                    "HOME": "/nonexistent",
                    "LANG": "C",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONNOUSERSITE": "1",
                },
            )
        self.assertEqual(completed.returncode, 0)

    def test_renderer_fails_closed_on_unsupported_platform(self):
        with (
            patch.object(renderer.sys, "platform", "win32"),
            patch.object(renderer.subprocess, "run") as run,
        ):
            with self.assertRaises(renderer.MaximumPDFRenderError) as error:
                renderer.render_isolated_pdf_page(self.pdf, 0)
        self.assertEqual(str(error.exception), renderer.BLOCK_MESSAGE)
        run.assert_not_called()

    @unittest.skipUnless(sys.platform == "darwin", "Requires macOS filesystem confinement")
    def test_child_starts_with_isolation_flags_and_private_bytes(self):
        real_run = subprocess.run
        calls = []
        def observe(command, **kwargs):
            calls.append((tuple(command), kwargs.copy()))
            return real_run(command, **kwargs)
        with patch.object(renderer.subprocess, "run", side_effect=observe):
            renderer.render_isolated_pdf_page(self.pdf, 0)
        command, opts = calls[0]
        self.assertEqual(command[:3], (
            renderer.SANDBOX_EXEC, "-p", renderer.RENDERER_FILESYSTEM_PROFILE,
        ))
        self.assertIn("(deny default)", command[2])
        python_index = command.index(str(Path(sys.executable).resolve()))
        self.assertEqual(command[python_index:python_index + 3],
                         (str(Path(sys.executable).resolve()), "-I", "-B"))
        self.assertTrue(command[-2].endswith("maximum_render_worker.py"))
        self.assertEqual(command[-1], "0")
        self.assertIs(opts["input"], self.pdf)
        self.assertEqual(opts["cwd"], "/")
        self.assertTrue(opts["close_fds"])
        self.assertTrue(opts["start_new_session"])
        self.assertEqual(opts["stderr"], subprocess.DEVNULL)
        self.assertEqual(opts["timeout"], renderer.WORKER_WALL_SECONDS)
        self.assertEqual(set(opts["env"]), {
            "PATH", "HOME", "LANG", "PYTHONDONTWRITEBYTECODE",
            "PYTHONNOUSERSITE", "PDF_MAGIC_RENDER_NETWORK_SANDBOX",
        })
        self.assertEqual(opts["env"]["PDF_MAGIC_RENDER_NETWORK_SANDBOX"], "seatbelt-v1")

    @unittest.skipUnless(sys.platform == "darwin", "Requires macOS filesystem confinement")
    def test_bad_pdf_and_out_of_range_page_fail_closed(self):
        for data, page in ((b"%PDF-1.4\nPrivate content", 0), (self.pdf, 2),
                           (b"%PDF-1.4\n", 0)):
            with self.subTest(page=page), self.assertRaises(
                renderer.MaximumPDFRenderError
            ) as failure:
                renderer.render_isolated_pdf_page(data, page)
            self.assertEqual(str(failure.exception), renderer.BLOCK_MESSAGE)
            self.assertNotIn("Private", str(failure.exception))

    @unittest.skipUnless(sys.platform == "darwin", "Requires macOS filesystem confinement")
    def test_password_protected_document_is_not_rendered(self):
        doc = pymupdf.open(stream=self.pdf, filetype="pdf")
        locked = doc.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="hidden-owner", user_pw="hidden-user",
        )
        doc.close()
        with self.assertRaises(renderer.MaximumPDFRenderError) as e:
            renderer.render_isolated_pdf_page(locked, 0)
        self.assertEqual(str(e.exception), renderer.BLOCK_MESSAGE)

    def test_timeout_crash_and_missing_worker_fail_closed_without_details(self):
        for error in (subprocess.TimeoutExpired("private", 1),
                      OSError("/private/filename.pdf"), RuntimeError("secret")):
            with self.subTest(error=type(error).__name__), \
                    patch.object(renderer, "_renderer_command", return_value=("trusted-worker",)), \
                    patch.object(renderer.subprocess, "run", side_effect=error), \
                    self.assertRaises(renderer.MaximumPDFRenderError) as failure:
                renderer.render_isolated_pdf_page(self.pdf, 0)
            self.assertEqual(str(failure.exception), renderer.BLOCK_MESSAGE)
        with patch.object(renderer, "_renderer_command", return_value=("trusted-worker",)), \
                patch.object(
                    renderer.subprocess, "run",
                    return_value=subprocess.CompletedProcess([], 137, b""),
                ), self.assertRaises(renderer.MaximumPDFRenderError):
            renderer.render_isolated_pdf_page(self.pdf, 0)

    def test_rejects_forged_protocol_and_oversized_output(self):
        # This protocol test needs a valid PNG fixture, not another worker
        # launch; real child rasterization is verified in dedicated tests.
        document = pymupdf.open(stream=self.pdf, filetype="pdf")
        try:
            png = document[0].get_pixmap(
                colorspace=pymupdf.csRGB, alpha=False, annots=False,
            ).tobytes("png")
        finally:
            document.close()
        valid = frame(png)
        broken = (
            b"", b"notpng", valid + b"tampered", valid[:-1],
            valid.replace(renderer.MAGIC, b"BADMAGC1", 1),
            frame(png, permitsOpen=True),
            frame(png, pageIndex=1),
            frame(png, pageCount=True),
            frame(png, width=0),
            frame(png, width=True),
            frame(png, workerPid=-5),
            frame(png, secret="private.pdf"),
            struct.pack(">8sII", renderer.MAGIC, 1,
                        renderer.MAX_PNG_BYTES + 1) + b"x",
            b"X" * (renderer.MAX_PNG_BYTES + renderer.MAX_METADATA_BYTES + 17),
        )
        for output in broken:
            with self.subTest(size=len(output)), \
                    patch.object(renderer, "_renderer_command", return_value=("trusted-worker",)), \
                    patch.object(
                        renderer.subprocess, "run",
                        return_value=subprocess.CompletedProcess([], 0, output),
                    ), self.assertRaises(renderer.MaximumPDFRenderError):
                renderer.render_isolated_pdf_page(self.pdf, 0)

    def test_response_is_immutable_and_non_authorizing(self):
        document = pymupdf.open(stream=self.pdf, filetype="pdf")
        try:
            png = document[0].get_pixmap(
                colorspace=pymupdf.csRGB, alpha=False, annots=False,
            ).tobytes("png")
        finally:
            document.close()
        r = renderer.RenderedPDFPage(0, 2, 200, 150, os.getpid() + 1, png)
        meta = r.to_metadata()
        self.assertEqual(meta["pngBytes"], len(r.png_bytes))
        self.assertFalse(meta["permitsOpen"])
        meta["pageCount"] = 99
        self.assertEqual(r.to_metadata()["pageCount"], 2)
        with self.assertRaises(FrozenInstanceError):
            r.png_bytes = b"tampered"
        with self.assertRaises(ValueError):
            renderer.RenderedPDFPage(
                r.page_index, r.page_count, r.width, r.height,
                r.worker_pid, r.png_bytes, permits_open=True,
            )

    def test_direct_worker_rejects_bad_commands_without_output(self):
        worker = ROOT / "maximum_render_worker.py"
        for index, contents in (("false", self.pdf), ("-1", self.pdf),
                                ("0", b"garbage"), ("3", self.pdf)):
            with self.subTest(index=index):
                finished = subprocess.run(
                    (sys.executable, "-I", "-B", str(worker), index),
                    input=contents, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, timeout=15, cwd="/",
                )
                self.assertNotEqual(finished.returncode, 0)
                self.assertEqual(finished.stdout, b"")

    def test_worker_applies_limits_before_raster_import_and_deployed_gate_untouched(self):
        worker = (ROOT / "maximum_render_worker.py").read_text()
        self.assertLess(worker.index("_apply_limits()"), worker.index("import pymupdf"))
        self.assertLess(worker.index("apply_linux_network_denial()"),
                        worker.index("import pymupdf"))
        self.assertLess(worker.index("apply_linux_network_denial()"),
                        worker.index("document_bytes = sys.stdin.buffer.read"))
        linux_fs_guard = worker.index(
            "Linux currently lacks the parent-enforced renderer filesystem"
        )
        self.assertLess(linux_fs_guard, worker.index("document_bytes = sys.stdin.buffer.read"))
        self.assertLess(linux_fs_guard, worker.index("import pymupdf"))
        self.assertIn('os.environ.get("PDF_MAGIC_RENDER_NETWORK_SANDBOX")', worker)
        self.assertIn("annots=False", worker)
        self.assertIn("MAX_RENDER_PIXELS", worker)
        self.assertIn("doc.needs_pass", worker)
        scan = (ROOT / "scan-and-open.py").read_text()
        self.assertNotIn("maximum_render_worker", scan)
        self.assertNotIn("maximum_isolated_renderer", scan)
        self.assertIn("if not cached_clean(cache_id):", scan)
        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.MAXIMUM].selectable)

    @unittest.skipUnless(sys.platform == "darwin", "Late SIGALRM is macOS-only")
    def test_worker_alarm_is_disarmed_before_process_shutdown(self):
        # Regression: the worker used to emit a complete PNG and then die
        # from SIGALRM during Python interpreter teardown.
        for i in range(16):
            with self.subTest(attempt=i):
                page = renderer.render_isolated_pdf_page(self.pdf, 0)
                self.assertEqual(page.page_index, 0)
                self.assertTrue(page.png_bytes.startswith(renderer.PNG_SIGNATURE))

    def test_ci_checks_renderer_filesystem_confinement(self):
        ci = (ROOT / ".github/workflows/maximum-isolated-renderer.yml").read_text()
        self.assertIn("ubuntu-latest", ci)
        self.assertIn("macos-latest", ci)
        self.assertIn("test-maximum-isolated-renderer.py -v", ci)
        self.assertIn("pymupdf==2.0", ci)
        self.assertTrue((ROOT / "maximum_render_filesystem_probe.py").is_file())

    def test_filesystem_policy_is_deny_by_default_and_read_only(self):
        profile = renderer.RENDERER_FILESYSTEM_PROFILE
        self.assertIn("(deny default)", profile)
        self.assertIn('(literal (param "PYTHON"))', profile)
        self.assertIn('(literal (param "WORKER_SUPPORT"))', profile)
        self.assertIn('(literal (param "NETWORK_SUPPORT"))', profile)
        self.assertIn('(literal (param "RENDERER_SUPPORT"))', profile)
        self.assertNotIn('(subpath (param "WORKER_DIR"))', profile)
        self.assertIn('(subpath (param "PYTHON_PREFIX"))', profile)
        self.assertIn("(deny network*)", profile)
        self.assertIn("(deny process-fork)", profile)
        self.assertNotIn("(allow default)", profile)
        self.assertNotIn("(allow file-write", profile)
        self.assertNotIn('(subpath "/Users")', profile)
        self.assertNotIn('(subpath "/private/tmp")', profile)
        self.assertNotIn('(subpath "/private/var")', profile)
        content_rules = profile.replace(
            '(allow file-read-metadata (subpath "/"))', ""
        )
        self.assertNotIn('(subpath "/")', content_rules)

    def test_renderer_fails_closed_without_macos_filesystem_sandbox(self):
        with (
            patch.object(renderer.sys, "platform", "linux"),
            patch.object(renderer.subprocess, "run") as run,
        ):
            with self.assertRaises(renderer.MaximumPDFRenderError) as error:
                renderer.render_isolated_pdf_page(self.pdf, 0)
        self.assertEqual(str(error.exception), renderer.BLOCK_MESSAGE)
        run.assert_not_called()

    @unittest.skipUnless(sys.platform == "darwin", "Requires macOS filesystem confinement")
    def test_renderer_sandbox_context_trusts_only_valid_runtime_paths(self):
        source_root = Path(__file__).resolve().parent
        worker = source_root / "maximum_render_worker.py"
        support_files = (
            source_root / "maximum_isolated_worker.py",
            source_root / "maximum_network_isolation.py",
            source_root / "maximum_isolated_renderer.py",
        )
        python = str(Path(sys.executable).resolve(strict=True))
        prefix = str(Path(sys.prefix).resolve(strict=True))
        base_prefix = str(Path(sys.base_prefix).resolve(strict=True))
        checks = {
            "sandbox executable": renderer._trusted_regular_file(
                renderer.SANDBOX_EXEC, executable=True
            ),
            "python executable": renderer._trusted_regular_file(
                python, executable=True
            ),
            "worker": renderer._trusted_regular_file(str(worker.resolve(strict=True))),
            "source root": renderer._trusted_directory(str(source_root)),
            "python prefix": renderer._trusted_directory(prefix, runtime=True),
            "base prefix": renderer._trusted_directory(base_prefix, runtime=True),
        }
        checks.update({
            "support " + path.name: renderer._trusted_regular_file(
                str(path.resolve(strict=True))
            )
            for path in support_files
        })
        self.assertTrue(all(checks.values()), checks)
        context = renderer._renderer_sandbox_context(worker)
        self.assertEqual(context["worker"], str(worker.resolve(strict=True)))

    def test_renderer_rejects_worker_outside_trusted_directory(self):
        with tempfile.TemporaryDirectory(prefix="opener-render-outside-") as directory:
            outside_worker = Path(directory) / "worker.py"
            outside_worker.write_text("pass", encoding="utf-8")
            with (
                patch.object(renderer.sys, "platform", "darwin"),
                self.assertRaises(renderer.MaximumPDFRenderError) as error,
            ):
                renderer._renderer_sandbox_context(outside_worker)
        self.assertEqual(str(error.exception), renderer.BLOCK_MESSAGE)

    @unittest.skipUnless(sys.platform == "darwin", "Requires actual macOS Seatbelt enforcement")
    def test_real_sandbox_denies_private_file_reads_and_writes(self):
        with tempfile.TemporaryDirectory(prefix="opener-render-private-") as directory:
            private_root = Path(directory)
            private = private_root / "private.pdf"
            private.write_bytes(b"private marker")
            write_target = private_root / "should-not-exist"
            probe = ROOT / "maximum_render_filesystem_probe.py"
            command = filesystem_sandbox_command(probe, str(private), str(write_target))
            outcome = subprocess.run(
                command, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=renderer.WORKER_WALL_SECONDS, check=False,
                close_fds=True, start_new_session=True, cwd="/",
                env={
                    "PATH": "/usr/bin:/bin",
                    "HOME": "/nonexistent",
                    "LANG": "C",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONNOUSERSITE": "1",
                },
            )
            self.assertEqual(outcome.returncode, 0)
            self.assertEqual(private.read_bytes(), b"private marker")
            self.assertFalse(write_target.exists())

if __name__ == "__main__":
    unittest.main()
