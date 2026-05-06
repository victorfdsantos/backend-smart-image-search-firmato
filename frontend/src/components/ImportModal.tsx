"use client";
import { useState } from "react";
import { Upload, CheckCircle, Brain, FileText } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import type { UploadStats } from "@/types";

interface ImportModalProps {
  open: boolean;
  onClose: () => void;
}

type State =
  | { kind: "idle" }
  | { kind: "uploading" }
  | { kind: "retraining" }
  | { kind: "success"; stats?: UploadStats }
  | { kind: "error"; message: string };

function StatRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between py-1 border-b border-firmato-border last:border-b-0">
      <span className="font-lato text-sm text-firmato-muted">{label}</span>
      <span className="font-lato text-sm font-semibold text-firmato-text">
        {value}
      </span>
    </div>
  );
}

export function ImportModal({ open, onClose }: ImportModalProps) {
  const [state, setState] = useState<State>({ kind: "idle" });

  const handleClose = () => {
    setState({ kind: "idle" });
    onClose();
  };

  const doProcess = async () => {
    setState({ kind: "uploading" });

    try {
      const result = await fetch("/api/catalog/register", {
        method: "POST",
      }).then(res => res.json());

      if (!result || result.detail) {
        setState({ kind: "error", message: result?.detail ?? "Erro inesperado." });
        return;
      }

      setState({ kind: "success", stats: result });
    } catch (e) {
      setState({ kind: "error", message: `Erro: ${e}` });
    }
  };

  const doRetrain = async () => {
    setState({ kind: "retraining" });
    try {
      const res = await fetch("/api/catalog/retrain", { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setState({ kind: "success" });
    } catch (e) {
      setState({ kind: "error", message: `Erro no retreinamento: ${e}` });
    }
  };

  const isLoading = state.kind === "uploading" || state.kind === "retraining";

  return (
    <Modal open={open} onClose={handleClose} title="Sincronizar Catálogo">
      {isLoading ? (
        <div className="flex flex-col items-center gap-3 py-10">
          <Spinner className="w-8 h-8" />
          <p className="font-lato text-sm font-medium text-firmato-text">
            {state.kind === "retraining"
              ? "Recarregando sistema..."
              : "Sincronizando catálogo..."}
          </p>
          <p className="font-lato text-xs text-firmato-muted text-center">
            Isso pode levar alguns minutos.
          </p>
        </div>
      ) : state.kind === "success" ? (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <CheckCircle size={22} className="text-green-500" />
            <p className="font-lato text-[15px] font-semibold text-firmato-text">
              {state.stats ? "Processamento concluído" : "Recarregamento concluído"}
            </p>
          </div>

          <div className="border-t border-firmato-border" />

          {state.stats ? (
            <div>
              <StatRow label="Total de linhas" value={state.stats.total} />
              <StatRow label="Novos produtos" value={state.stats.novos} />
              <StatRow label="Imagens atualizadas" value={state.stats.imagem_principal_atualizada} />
              <StatRow label="Secundárias processadas" value={state.stats.secundarias_processadas} />
              <StatRow label="Secundárias deletadas" value={state.stats.secundarias_deletadas} />
              <StatRow label="Pastas movidas no NAS" value={state.stats.pasta_nas_movida} />
              <StatRow label="Dados atualizados" value={state.stats.dados_atualizados} />
              <StatRow label="Ignorados" value={state.stats.ignorados} />
              <StatRow label="Erros" value={state.stats.erros} />
              <StatRow label="Arquivos limpos" value={state.stats.arquivos_limpos} />
            </div>
          ) : (
            <p className="font-lato text-sm text-firmato-muted">
              Sistema recarregado com sucesso.
            </p>
          )}

          <div className="flex gap-3 pt-2">
            {state.stats && (
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => window.open("/api/catalog/latest-log", "_blank")}
              >
                <FileText size={14} />
                Baixar Log
              </Button>
            )}
            <Button variant="solid" className="flex-1" onClick={handleClose}>
              Fechar
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <p className="font-lato text-sm text-firmato-muted">
            Este processo sincroniza automaticamente o catálogo com o SharePoint.
          </p>

          {state.kind === "error" && (
            <p className="font-lato text-xs text-red-600">{state.message}</p>
          )}

          <div className="flex gap-3">
            <Button variant="solid" className="flex-1" onClick={doProcess}>
              <Upload size={14} />
              Processar Catálogo
            </Button>

            <Button variant="outline" className="flex-1" onClick={doRetrain}>
              <Brain size={14} />
              Recarregar Sistema
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}