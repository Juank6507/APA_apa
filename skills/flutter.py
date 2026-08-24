# apa/skills/flutter.py

SKILL = {
    "name": "flutter",
    "language": "dart",
    "keywords": ["flutter", "dart", "widget", "setstate", "material", "cupertino", "bloc", "provider", "riverpod", "async", "await", "future", "stream", "test"],
    "prompt_fragment": """**Flutter/Dart Best Practices:**
- Use `const` constructors where possible.
- Prefer `StatelessWidget` for static UI.
- Handle async with `FutureBuilder` or `async/await`.
- Example:
  ```dart
  import 'package:flutter/material.dart';
  void main() => runApp(const MyApp());
  class MyApp extends StatelessWidget {
    const MyApp({super.key});
    @override
    Widget build(BuildContext context) {
      return MaterialApp(
        home: Scaffold(
          body: Center(child: Text('OK')),
        ),
      );
    }
  }
  ```""",
    "example_code": """
import 'package:flutter/material.dart';

void main() => runApp(const MyApp());

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      home: Scaffold(
        appBar: AppBar(title: const Text('Flutter Demo')),
        body: const Center(child: Text('CRITERIO OK')),
      ),
    );
  }
}
"""
}

if __name__ == "__main__":
    assert "SKILL" in globals()
    skill = SKILL
    required = ["name", "language", "keywords", "prompt_fragment"]
    for key in required:
        assert key in skill
    assert skill["language"] == "dart"
    print("CRITERIO OK")