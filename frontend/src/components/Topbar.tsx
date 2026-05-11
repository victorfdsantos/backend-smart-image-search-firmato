"use client";
import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";

interface TopbarProps {
  onImport: () => void;
  onReset: () => void;
}

function LogoSvg() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="160"
      height="40"
      viewBox="0 0 160 40"
      aria-label="Firmato"
    >
      <text
        x="0"
        y="30"
        fontFamily="Georgia, serif"
        fontSize="26"
        fontWeight="900"
        letterSpacing="3"
        fill="#2c2c2c"
      >
        FIRMATO
      </text>
    </svg>
  );
}

function Logo({ onClick }: { onClick: () => void }) {
  const [useFallback, setUseFallback] = useState(false);

  return (
    <button
      onClick={onClick}
      className="h-10 flex items-center cursor-pointer opacity-100 hover:opacity-75 transition-opacity"
      title="Voltar ao início"
    >
      {useFallback ? (
        <LogoSvg />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src="/logo_cinza.png"
          alt="Firmato"
          height={40}
          className="h-10 w-auto object-contain"
          onError={() => setUseFallback(true)}
        />
      )}
    </button>
  );
}

function SobreModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Modal open={open} onClose={onClose} title="Sobre a Plataforma">
      <div className="space-y-5">
        <div className="space-y-3">
          <p className="font-lato text-sm text-firmato-text leading-relaxed">
            O <strong>Firmato Buscador de Imagens</strong> é uma plataforma interna de busca semântica
            para o catálogo de produtos Firmato Móveis.
          </p>
          <p className="font-lato text-sm text-firmato-muted leading-relaxed">
            A ferramenta permite localizar produtos por descrição textual ou por similaridade visual,
            utilizando o modelo CLIP para entender o conteúdo das imagens e relacioná-las às buscas.
          </p>
        </div>

        <div className="border-t border-firmato-border" />

        <div className="space-y-2">
          <p className="font-lato text-xs font-bold text-firmato-accent uppercase tracking-widest">
            Como funciona
          </p>
          <ul className="space-y-2">
            {[
              { titulo: "Busca por texto", desc: "Digite palavras-chave como 'sofá cinza modular' ou 'poltrona linho bege' e o sistema encontra os produtos mais similares semanticamente." },
              { titulo: "Busca por imagem", desc: "Faça upload de uma foto de referência e o sistema retorna os produtos visualmente mais parecidos do catálogo." },
              { titulo: "Busca combinada", desc: "Use texto e imagem juntos para resultados ainda mais precisos." },
              { titulo: "Filtros", desc: "Refine os resultados por marca, categoria, faixa de preço, ambiente, forma e material." },
              { titulo: "Atualizar Dados", desc: "Sincroniza o catálogo com o SharePoint, processa imagens e retreina os embeddings de busca automaticamente." },
            ].map(({ titulo, desc }) => (
              <li key={titulo} className="flex gap-2">
                <span className="text-firmato-accent mt-0.5 shrink-0">→</span>
                <p className="font-lato text-sm text-firmato-muted leading-relaxed">
                  <span className="font-semibold text-firmato-text">{titulo}:</span> {desc}
                </p>
              </li>
            ))}
          </ul>
        </div>

        <div className="border-t border-firmato-border" />

        <div className="flex items-center justify-between">
          <div>
            <p className="font-lato text-xs text-firmato-muted">
              Versão <span className="font-semibold text-firmato-text">1.0.0</span>
            </p>
            <p className="font-lato text-xs text-firmato-muted mt-0.5">
              Desenvolvido por{" "}
              <span className="font-semibold text-firmato-text">Victor Fernandes</span>
            </p>
          </div>
          <Button variant="solid" size="sm" onClick={onClose}>
            Fechar
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export function Topbar({ onImport, onReset }: TopbarProps) {
  const [sobreOpen, setSobreOpen] = useState(false);

  return (
    <>
      <header className="sticky top-0 z-40 w-full bg-firmato-surface border-b border-firmato-border">
        <div className="flex items-center justify-between px-10 py-5">
          <Logo onClick={onReset} />
          <div className="flex items-center gap-3">
            <Button variant="solid" onClick={onImport}>
              <RefreshCw size={14} />
              Atualizar Dados
            </Button>
            <Button variant="outline" onClick={() => setSobreOpen(true)}>
              Sobre
            </Button>
          </div>
        </div>
      </header>

      <SobreModal open={sobreOpen} onClose={() => setSobreOpen(false)} />
    </>
  );
}