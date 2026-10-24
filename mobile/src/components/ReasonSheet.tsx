// Ask for a short reason (decline a job, report a problem). Android has no Alert.prompt, so this is a small modal.
import { useState } from "react";
import { Modal, Pressable, Text, TextInput } from "react-native";
import { colors } from "../theme";
import { Button, Chips } from "./ui";

export default function ReasonSheet({
  visible,
  title,
  presets,
  confirmLabel,
  onCancel,
  onConfirm,
}: {
  visible: boolean;
  title: string;
  presets: string[];
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: (reason: string) => void;
}) {
  const [preset, setPreset] = useState("");
  const [text, setText] = useState("");
  const reason = preset === "Other" ? text.trim() : preset;

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel}>
      <Pressable style={{ flex: 1, backgroundColor: "rgba(0,0,0,.4)", justifyContent: "flex-end" }} onPress={onCancel}>
        <Pressable style={{ backgroundColor: "#fff", borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 20, gap: 14 }} onPress={() => undefined}>
          <Text style={{ fontSize: 18, fontWeight: "800", color: colors.ink }}>{title}</Text>
          <Chips options={[...presets, "Other"].map((p) => ({ value: p, label: p }))} value={preset} onChange={setPreset} />
          {preset === "Other" ? (
            <TextInput
              accessibilityLabel="Reason"
              value={text}
              onChangeText={setText}
              placeholder="Write the reason"
              placeholderTextColor="#8A928E"
              maxLength={300}
              style={{ height: 48, borderWidth: 1, borderColor: colors.line2, borderRadius: 12, paddingHorizontal: 14, fontSize: 15, color: colors.ink }}
            />
          ) : null}
          <Button
            label={confirmLabel}
            variant="danger"
            disabled={reason.length < 3}
            onPress={() => {
              onConfirm(reason);
              setPreset("");
              setText("");
            }}
          />
          <Button label="Back" variant="outline" onPress={onCancel} />
        </Pressable>
      </Pressable>
    </Modal>
  );
}
