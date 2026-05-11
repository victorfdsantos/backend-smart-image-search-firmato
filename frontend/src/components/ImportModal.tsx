"use client";
import { useState } from "react";
import { CheckCircle, FileText, AlertTriangle, RefreshCw } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import type { UploadStats } from "@/types";

interface ImportModalProps {
  open: boolean;
  onClose: () => void;
}

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; stats: UploadStats; elapsed: number }
  | { kind: "error"; message: string };

function StatRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-firmato-border last:border-b-0">
      <span className="font-lato text-sm text-firmato-muted">{label}</span>
      <span
        className={`font-lato text-sm font-semibold ${
          value > 0 ? "text-firmato-accent" : "text-firmato-text"
        }`}
      >
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

  const doUpdate = async () => {
    setState({ kind: "loading" });
    try {
      const res = await fetch("/api/catalog/register", { method: "POST" });
      const result = await res.json();

      if (!res.ok || result.detail) {
        setState({
          kind: "error",
          message: result?.detail ?? `Erro HTTP ${res.status}`,
        });
        return;
      }

      setState({
        kind: "success",
        stats: result,
        elapsed: result.elapsed_seconds ?? 0,
      });
    } catch (e) {
      setState({ kind: "error", message: `Erro inesperado: ${e}` });
    }
  };

  const downloadLog = () => {
    window.open("/api/catalog/latest-log", "_blank");
  };

  return (
    <Modal open={open} onClose={handleClose} title="Atualizar Catálogo">
      {state.kind === "idle" && (
        <div className="space-y-5">
          <p className="font-lato text-sm text-firmato-muted leading-relaxed">
            Sincroniza automaticamente o catálogo com o SharePoint, processa
            imagens novas ou alteradas e retreina os embeddings de busca.
          </p>
          <Button variant="solid" className="w-full" onClick={doUpdate}>
            <RefreshCw size={14} />
            Atualizar Dados
          </Button>
        </div>
      )}

      {state.kind === "loading" && (
        <div className="flex flex-col items-center gap-4 py-10">
          {/* Spinner animado */}
          <div className="relative w-12 h-12">
            <div className="absolute inset-0 rounded-full border-2 border-firmato-border" />
            <div className="absolute inset-0 rounded-full border-2 border-t-firmato-accent animate-spin" />
          </div>
          <div className="text-center space-y-1">
            <p className="font-lato text-sm font-semibold text-firmato-text">
              Atualizando...
            </p>
            <p className="font-lato text-xs text-firmato-muted">
              Sincronizando com SharePoint, processando imagens e retreinando
              embeddings. Isso pode levar alguns minutos.
            </p>
          </div>
        </div>
      )}

      {state.kind === "success" && (
        <div className="space-y-4">
          {/* Header de sucesso */}
          <div className="flex items-center gap-2">
            <CheckCircle size={20} className="text-green-500 shrink-0" />
            <div>
              <p className="font-lato text-[15px] font-semibold text-firmato-text">
                Atualização concluída
              </p>
              <p className="font-lato text-xs text-firmato-muted">
                {state.elapsed.toFixed(1)}s · embeddings recarregados
              </p>
            </div>
          </div>

          <div className="border-t border-firmato-border" />

          {/* Stats */}
          <div className="bg-firmato-bg p-4 space-y-0">
            <p className="font-lato text-[10px] font-bold text-firmato-accent uppercase tracking-widest mb-2">
              Resumo
            </p>
            <StatRow label="Produtos processados" value={state.stats.processed ?? 0} />
            <StatRow label="Ignorados (sem alteração)" value={state.stats.skipped ?? 0} />
            <StatRow label="Erros" value={state.stats.errors ?? 0} />
            {state.stats.updated_ids && (
              <div className="flex items-center justify-between py-1.5">
                <span className="font-lato text-sm text-firmato-muted">
                  IDs atualizados
                </span>
                <span className="font-lato text-sm font-semibold text-firmato-text">
                  {Array.isArray(state.stats.updated_ids)
                    ? state.stats.updated_ids.length
                    : 0}
                </span>
              </div>
            )}
          </div>

          {/* Botões */}
          <div className="flex gap-3 pt-1">
            <Button variant="outline" className="flex-1" onClick={downloadLog}>
              <FileText size={14} />
              Baixar Log
            </Button>
            <Button variant="solid" className="flex-1" onClick={handleClose}>
              Fechar
            </Button>
          </div>
        </div>
      )}

      {state.kind === "error" && (
        <div className="space-y-4">
          <div className="flex items-start gap-2">
            <AlertTriangle size={20} className="text-red-500 shrink-0 mt-0.5" />
            <div>
              <p className="font-lato text-[15px] font-semibold text-firmato-text">
                Falha na atualização
              </p>
              <p className="font-lato text-xs text-firmato-muted mt-1 leading-relaxed">
                {state.message}
              </p>
            </div>
          </div>

          <div className="flex gap-3 pt-1">
            <Button
              variant="outline"
              className="flex-1"
              onClick={() => setState({ kind: "idle" })}
            >
              Tentar novamente
            </Button>
            <Button variant="solid" className="flex-1" onClick={downloadLog}>
              <FileText size={14} />
              Ver Log
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}