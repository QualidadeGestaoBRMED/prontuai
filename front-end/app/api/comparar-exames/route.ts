import { NextRequest, NextResponse } from "next/server";
import OpenAI from "openai";

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY, // seguro no servidor
});

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    // Aceita tanto exames_ocr quanto examesOCRText, idem para BRNET
    let examesOCRText = body.examesOCRText || body.exames_ocr;
    let examesBRNETText = body.examesBRNETText || body.exames_brnet;

    // Se vierem como array, formate igual ao client antigo
    if (Array.isArray(examesOCRText)) {
      examesOCRText = examesOCRText.map((e: string) => `- ${e}`).join("\n");
    }
    if (Array.isArray(examesBRNETText)) {
      examesBRNETText = examesBRNETText.map((e: string) => `- ${e}`).join("\n");
    }

    console.log("API recebeu:", { examesOCRText, examesBRNETText });

    const prompt = `Compare as duas listas de exames abaixo. Use a lista do BRNET como referência principal. Para cada exame do BRNET, procure na lista do documento (OCR) se existe algum exame equivalente, mesmo que o nome seja diferente (exemplo: \"Hemograma completo\" e \"exame de sangue\" devem ser considerados equivalentes). Se encontrar, marque como presente e informe o nome correspondente do OCR. Se não encontrar, marque como ausente.\n\nExemplos de equivalência:\n- \"Hemograma completo\" e \"Hemograma completo com plaquetas\" são equivalentes.\n- \"Hemograma completo\" e \"exame de sangue\" são equivalentes.\n- \"Glicemia de jejum\" e \"glicemia\" são equivalentes.\n- \"Clínico ocupacional\" e \"consulta clínica ocupacional\" são equivalentes.\n\nPara cada exame do BRNET, retorne um objeto com:\n- exame: nome do exame do BRNET (exatamente como está na lista)\n- presente_no_brnet: true\n- presente_no_ocr: true/false\n- versao_brnet: \"Previsto\"\n- versao_ocr: nome do exame correspondente do OCR (ou \"Não encontrado\" se não houver)\n\nATENÇÃO: É OBRIGATÓRIO adicionar ao FINAL do array TODOS os exames do OCR que NÃO têm equivalente no BRNET, marcando:\n- presente_no_brnet: false\n- presente_no_ocr: true\n- versao_brnet: \"Não previsto\"\n- versao_ocr: nome do exame do OCR\n- exame: nome do exame do OCR\nSE VOCÊ NÃO ADICIONAR ESTES EXTRAS, A RESPOSTA ESTARÁ ERRADA.\n\nMe devolva um array JSON, onde cada objeto tem a seguinte estrutura (nessa ordem de colunas):\n[\n  {\n    \"exame\": \"Hemograma completo\",\n    \"presente_no_brnet\": true,\n    \"presente_no_ocr\": true,\n    \"versao_brnet\": \"Previsto\",\n    \"versao_ocr\": \"exame de sangue\"\n  }\n]\n\n⚠️ Me retorne apenas o array JSON, sem explicações extras, sem comentários, sem markdown.\n\nExames do documento (OCR):\n${examesOCRText}\n\nExames previstos pelo BRNET:\n${examesBRNETText}`;

    const response = await openai.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [
        { role: "system", content: "Você é um assistente médico que compara exames de prontuário com os autorizados pelo sistema BRNET." },
        { role: "user", content: prompt },
      ],
      temperature: 0.3,
      max_tokens: 3000,
    });

    let resposta = response.choices[0].message?.content?.trim() || "";
    console.log("Resposta bruta da OpenAI:", resposta);

    // Fallback/normalização de equivalências
    try {
      const parsed = JSON.parse(resposta);
      if (Array.isArray(parsed) && parsed[0]?.exame) {
        const normalize = (str: string) => str.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase().replace(/[^a-z0-9]/gi, " ").replace(/\s+/g, " ").trim();
        const equivalencias = {
          "hemograma completo com plaquetas": ["hemograma completo", "exame de sangue", "hemograma", "hc", "hemograma c/ plaquetas"],
          "hemograma completo": ["hemograma completo com plaquetas", "exame de sangue", "hemograma", "hc"],
          "exame de sangue": ["hemograma completo com plaquetas", "hemograma completo", "hemograma", "hc"],
          "glicemia de jejum": ["glicemia", "glicemia em jejum", "glicose de jejum"],
          "glicemia": ["glicemia de jejum", "glicose", "teste de glicose"],
          "colesterol total": ["colesterol total e fracoes", "perfil lipidico", "lipidograma"],
          "colesterol total e fracoes": ["colesterol total", "perfil lipidico", "lipidograma"],
          "perfil lipidico": ["colesterol total", "colesterol total e fracoes", "lipidograma", "hdl", "ldl", "triglicerideos"],
          "triglicerideos": ["perfil lipidico", "lipidograma"],
          "tsh": ["hormonio estimulante da tireoide", "exame de tireoide", "tsh basal", "tsh ultra sensível"],
          "t4 livre": ["tiroxina livre", "exame de tireoide", "t4l"],
          "funcao tireoidiana": ["tsh", "t4 livre", "painel tireoidiano"],
          "acido urico": ["uricemia", "exame de acido urico"],
          "creatinina": ["creatinina serica", "exame de creatinina"],
          "ureia": ["ureia serica", "exame de ureia"],
          "exame de urina tipo i": ["eas", "urina tipo 1", "urina rotina", "sumario de urina"],
          "eas": ["exame de urina tipo i", "urina tipo 1", "urina rotina", "sumario de urina"],
          "papanicolau": ["citologia oncologica", "preventivo", "exame preventivo"],
          "citologia oncologica": ["papanicolau", "preventivo", "exame preventivo"],
          "psa": ["antigeno prostatico especifico", "psa total"],
          "antigeno prostatico especifico": ["psa", "psa total"],
          "radiografia de torax": ["raio x de torax", "rx de torax", "radiografia toracica"],
          "raio x de torax": ["radiografia de torax", "rx de torax", "radiografia toracica"],
          "ecografia abdominal": ["ultrassom abdominal", "usg abdominal", "ultrassonografia abdominal"],
          "ultrassom abdominal": ["ecografia abdominal", "usg abdominal", "ultrassonografia abdominal"],
          "ressonancia magnetica do joelho": ["rm joelho", "ressonancia joelho", "rm de joelho"],
          "clinico ocupacional": ["consulta clinica ocupacional", "exame ocupacional", "medicina ocupacional"],
          "consulta clinica ocupacional": ["clinico ocupacional", "exame ocupacional", "medicina ocupacional"],
        };
        const examesOCR = parsed.filter(e => e.presente_no_ocr && !e.presente_no_brnet).map(e => e.versao_ocr || e.exame);
        for (const item of parsed) {
          if (item.presente_no_brnet && !item.presente_no_ocr) {
            const normBRNET = normalize(item.exame);
            let found = false;
            for (const [key, aliases] of Object.entries(equivalencias)) {
              if (normalize(key) === normBRNET || aliases.some(a => normalize(a) === normBRNET)) {
                for (const ocr of examesOCR) {
                  const normOCR = normalize(ocr);
                  if (normalize(key) === normOCR || aliases.some(a => normalize(a) === normOCR)) {
                    item.presente_no_ocr = true;
                    item.versao_ocr = ocr;
                    found = true;
                    break;
                  }
                }
              }
              if (found) break;
            }
            if (!found) {
              for (const ocr of examesOCR) {
                const normOCR = normalize(ocr);
                if (normBRNET.includes(normOCR) || normOCR.includes(normBRNET)) {
                  item.presente_no_ocr = true;
                  item.versao_ocr = ocr;
                  break;
                }
              }
            }
          }
        }
        const previstosNorm = new Set(parsed.filter(e => e.presente_no_brnet).map(e => normalize(e.versao_ocr || e.exame)));
        const seenExtras = new Set();
        const deduped = parsed.filter((e) => {
          if (e.presente_no_brnet) return true;
          const norm = normalize(e.versao_ocr || e.exame);
          if (previstosNorm.has(norm)) return false;
          if (seenExtras.has(norm)) return false;
          seenExtras.add(norm);
          return true;
        });
        resposta = JSON.stringify(deduped);
      }
    } catch {}

    return NextResponse.json({ result: JSON.parse(resposta) });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Erro desconhecido';
    return NextResponse.json({ error: message }, { status: 500 });
  }
} 