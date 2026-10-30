---
name: reels-legendado
description: Transforma um vídeo bruto (pessoa falando para a câmera) em reel 9:16 pronto para postar - corta silêncios e pausas, transcreve em português e queima legenda animada com a palavra falada destacada. Use quando pedirem para editar, legendar, cortar pausas ou preparar um vídeo para Reels, TikTok ou Shorts.
---

# Reels legendado

Um comando faz tudo, com `scripts/reels.py`:

1. **Corta silêncios** (ffmpeg `silencedetect`), deixando um respiro curto em cada fala.
2. **Transcreve** com faster-whisper, com tempo de cada palavra.
3. **Gera a legenda** em grupos de 3 palavras, MAIÚSCULAS, com a palavra falada em destaque.
4. **Renderiza** em 1080x1920 (vídeo deitado é cortado pelo centro), H.264 + AAC, 30 fps.

## Requisitos

- `ffmpeg` (com libass, que vem no ffmpeg normal)
- Python 3 e `pip install faster-whisper`. Na primeira vez, ele baixa o modelo do Whisper.

Confira com `ffmpeg -version` e `python3 -c "import faster_whisper"` antes de rodar. Se faltar algo, diga à pessoa o comando de instalação. Não instale nada sem ela pedir.

## Uso

```bash
python3 .claude/skills/reels-legendado/scripts/reels.py video.mp4
```

Gera `video_reel.mp4`, mais:
- `video_reel.words.json`: a transcrição, editável
- `video_reel_cortado.mp4`: o vídeo já sem pausas e sem legenda

### Corrigir palavras erradas na legenda

O Whisper erra nomes e gírias. Corrija o texto no `.words.json` (não mexa nos tempos) e rode de novo **sobre o vídeo cortado**, para os tempos baterem:

```bash
python3 .claude/skills/reels-legendado/scripts/reels.py video_reel_cortado.mp4 \
  --words video_reel.words.json -o video_reel.mp4
```

### Opções úteis

| Opção | Padrão | Para quê |
|---|---|---|
| `--no-cut` | — | não cortar pausas |
| `--min-silence` | 0.5 | pausa mínima (s) que é cortada; aumente se ficar picotado |
| `--silence-db` | -35 | suba para -30 em ambiente barulhento |
| `--pad` | 0.12 | respiro mantido em volta da fala |
| `--model` | small | `medium` acerta mais e é mais lento; `base` é mais rápido |
| `--words-per-line` | 3 | palavras por vez na tela |
| `--font` / `--size` | Arial / 84 | fonte e tamanho (a fonte precisa estar instalada) |
| `--color` / `--highlight` | #FFFFFF / #FFD400 | cor do texto e da palavra ativa |
| `--position` | 0.72 | altura da legenda (0 topo, 1 base); fuja da área dos botões do app |
| `--no-uppercase` | — | manter maiúsculas e minúsculas originais |
| `--no-captions` | — | só cortar e converter para 9:16 |

## Como conduzir

1. Pergunte só o que faltar: o arquivo e, se a pessoa tiver, o estilo (cores da marca, fonte).
2. Rode com os padrões primeiro.
3. **Confira antes de entregar:** extraia 2 ou 3 quadros (`ffmpeg -ss <s> -i saida.mp4 -frames:v 1 q.png`) e veja se a legenda está legível, fora do rosto e sem palavras erradas. Leia o `.words.json` procurando nomes e termos errados.
4. Mostre à pessoa o quanto foi cortado e os erros de transcrição que encontrou, e ofereça a correção.

## Limites

- Corta só pausas, não escolhe o melhor take nem tira frases repetidas. Para isso, leia o `.words.json`, proponha os trechos a remover e faça o corte com ffmpeg depois que a pessoa aprovar.
- Vídeo deitado vira 9:16 cortando as laterais, então quem estiver fora do centro pode sair do quadro.
- Para animações mais elaboradas (emojis, títulos, motion graphics), use as skills `remotion-captions` ou `hyperframes`.
