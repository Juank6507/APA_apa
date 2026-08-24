# apa/skills/react_native.py

SKILL = {
    "name": "react_native",
    "language": "react-native",
    "keywords": ["react-native", "expo", "mobile", "ios", "android", "component", "navigation", "hook", "usestate", "useeffect", "flatlist", "stylesheet", "jest", "detox"],
    "prompt_fragment": """**React Native Best Practices:**
- Use functional components and React Hooks.
- Style with `StyleSheet.create()`.
- Use `Platform.select()` for iOS/Android differences.
- Example:
  ```jsx
  import React from 'react';
  import { View, Text, StyleSheet } from 'react-native';
  const App = () => (
    <View style={styles.container}>
      <Text style={styles.text}>OK</Text>
    </View>
  );
  const styles = StyleSheet.create({
    container: { flex: 1, justifyContent: 'center', alignItems: 'center' },
    text: { fontSize: 20 }
  });
  export default App;
  ```""",
    "example_code": """
import React, { useState } from 'react';
import { View, Text, Button, StyleSheet } from 'react-native';

const Counter = () => {
    const [count, setCount] = useState(0);
    return (
        <View style={styles.container}>
            <Text style={styles.text}>Contador: {count}</Text>
            <Button title="Incrementar" onPress={() => setCount(count + 1)} />
        </View>
    );
};

const styles = StyleSheet.create({
    container: { flex: 1, justifyContent: 'center', alignItems: 'center' },
    text: { fontSize: 20, marginBottom: 10 }
});

export default Counter;
"""
}

if __name__ == "__main__":
    assert "SKILL" in globals(), "Variable SKILL no encontrada"
    skill = SKILL
    for key in ["name", "language", "keywords", "prompt_fragment"]:
        assert key in skill, f"Falta clave: {key}"
    assert skill["language"] == "react-native"
    print("CRITERIO OK")