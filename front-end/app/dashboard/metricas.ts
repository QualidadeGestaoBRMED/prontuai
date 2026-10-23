/**
 * Derivação dos indicadores do dashboard.
 *
 * Não toca em React nem em fetch: recebe `DadosDashboard` mais os filtros da
 * tela e devolve tudo já formatado em pt-BR, pronto para renderizar. Manter a
 * conta aqui é o que permite trocar a origem dos dados (JSON estático hoje,
 * consulta no back-end depois) sem mexer na tela.
 */
import { CATEGORIAS_EXAME, MOTIVOS_EXTERNOS, OPCOES_EXAME, type MotivoExterno } from "@/types/feedback";

import type {
  CasoErroExame,
  ClinicaDados,
  CredenciadoPrevisto,
  DadosDashboard,
  PrevisaoDia,
  PontoAcuracia,
  PontoSerie,
  Prazos,
  SerieKey,
} from "./tipos";

// ── paleta ───────────────────────────────────────────────────────────────────
export const CORES = {
  tinta: "#193B4F",
  petroleo: "#007891",
  turquesa: "#00AFAA",
  agua: "#7EBFCC",
  positivo: "#2CAD6E",
  negativo: "#B4453A",
  alerta: "#CC851E",
  neutro: "#767A7B",
  borda: "#DFE0E2",
  fundo: "#F3F3F3",
} as const;

const POS = CORES.positivo;
const NEG = CORES.negativo;
const MUTED = CORES.neutro;
const CORES_RANK = ["#193B4F", "#007891", "#007891", "#00AFAA", "#00AFAA", "#7EBFCC"];

// ── filtros ──────────────────────────────────────────────────────────────────
export type FiltroPeriodo = "Semanal" | "Mensal" | "Trimestral" | "Tudo";
export type Aba = "utilizacao" | "acuracia";

/**
 * Cada filtro define DUAS coisas: o período dos indicadores (KPIs, ranking e
 * tabela) e a série de contexto mostrada nos gráficos de barra.
 *   periodo.serie / periodo.n -> quantos pontos entram nos números
 *   grafico.serie / grafico.n -> quantos pontos aparecem nas barras (0 = todos)
 */
const PERIODOS: Record<
  FiltroPeriodo,
  { label: string; periodo: { serie: SerieKey; n: number }; grafico: { serie: SerieKey; n: number } }
> = {
  Semanal: { label: "Semana", periodo: { serie: "semanal", n: 1 }, grafico: { serie: "semanal", n: 8 } },
  Mensal: { label: "Mês", periodo: { serie: "mensal", n: 1 }, grafico: { serie: "mensal", n: 6 } },
  Trimestral: { label: "3 meses", periodo: { serie: "mensal", n: 3 }, grafico: { serie: "mensal", n: 6 } },
  Tudo: { label: "Tudo", periodo: { serie: "mensal", n: 0 }, grafico: { serie: "mensal", n: 0 } },
};

/**
 * Janela do card "Pedidos previstos", em dias contados a partir de hoje.
 *
 * Os gráficos e KPIs olham para TRÁS; previsão de liberação olha para frente, e
 * as duas janelas não podem ser a mesma. O card reaproveita o filtro já
 * escolhido na tela — não há seletor nem período próprio — e a duração dele vira
 * o alcance para frente, com teto de um mês: previsão do BRNET a mais de 30 dias
 * é rara e instável (o prazo do credenciado é de 1 a 3 dias úteis após o
 * atendimento), então "3 meses" e "Tudo" mostrariam uma cauda sem uso
 * operacional. Por isso os dois caem no mesmo teto.
 */
const JANELA_PREVISTOS: Record<FiltroPeriodo, number> = {
  Semanal: 7,
  Mensal: 30,
  Trimestral: 30,
  Tudo: 30,
};

export const ORDEM_FILTROS: FiltroPeriodo[] = ["Semanal", "Mensal", "Trimestral", "Tudo"];

export const ROTULO_FILTRO = (f: FiltroPeriodo) => PERIODOS[f].label;

export const ABAS: { id: Aba; label: string }[] = [
  { id: "utilizacao", label: "Utilização" },
  { id: "acuracia", label: "Acurácia" },
];

// ── textos de apoio ──────────────────────────────────────────────────────────
const TIPS_KPI: Record<string, string> = {
  "Envios realizados": "Prontuários recebidos pela plataforma no período.",
  "Análises realizadas":
    "Aprovados ou rejeitados por uma pessoa do time BR MED (checador, gestor ou administrador). A decisão automática da IA não conta.",
  "Análises pendentes":
    "Envios realizados menos análises realizadas: prontuários que nenhuma pessoa do time BR MED aprovou ou rejeitou. Inclui os aprovados automaticamente, os que deram erro no processamento e os que a IA marcou com exame faltante.",
};

const TIPS_ACC: Record<string, string> = {
  Acurácia:
    "Quantas vezes a IA e o revisor chegaram à mesma conclusão. Clique no ? para ver o cálculo.",
  "Concordância direta":
    "Só os casos em que IA e revisor concordaram de imediato, sem contar as decisões resolvidas por motivo externo.",
  "Aprovações derrubadas":
    "A IA liberou e o revisor barrou. É o erro com consequência: sem revisão, o documento teria passado.",
  "Falhas técnicas":
    "A IA não conseguiu ler o CPF/CNPJ ou achar o paciente. Não é julgamento, por isso fica fora da acurácia.",
  "Acurácia por exame":
    "Do parecer do revisor no modal de feedback: exame a exame, onde a IA errou. Clique no número para ver por exame.",
};

/**
 * O processo por trás de cada indicador, aberto pelo "?" do card.
 *
 * Existe para a resposta estar na tela quando alguém pergunta numa reunião
 * "isso conta o quê?". Por isso cada entrada diz o que entra, o que fica de
 * fora e em que período o número cai — as três perguntas que de fato aparecem —,
 * em vez de descrever a consulta.
 *
 * Um card que reaproveita a conta de outro aponta para a mesma entrada: duas
 * explicações do mesmo número acabariam divergindo.
 *
 * Ao mudar uma regra em `dashboard_indicadores.sql`, em `dashboard_service.py`
 * ou neste arquivo, atualize o texto aqui junto — é ele que vai ser lido em voz
 * alta.
 */
export type IdIndicador =
  | "enviados"
  | "revisados"
  | "pendentes"
  | "expedicoes"
  | "ranking"
  | "prazoClinica"
  | "prazoTecnico"
  | "usandoPouco"
  | "valeIncluir"
  | "acuracia"
  | "concordancia"
  | "derrubadas"
  | "falhas"
  | "motivos"
  | "matriz"
  | "acuraciaExame";

export interface ComoCalculamos {
  titulo: string;
  /** A pergunta que o indicador responde, em uma linha. */
  pergunta: string;
  blocos: { titulo: string; texto: string }[];
}

export const RODAPE_COMO_CALCULAMOS =
  "Todos os números do painel são recalculados uma vez por dia, às 7h (horário de Brasília), e quando alguém aperta Atualizar.";

export const COMO_CALCULAMOS: Record<IdIndicador, ComoCalculamos> = {
  enviados: {
    titulo: "Envios realizados",
    pergunta: "Quanto as clínicas estão usando a plataforma.",
    blocos: [
      {
        titulo: "O que conta",
        texto:
          "Cada prontuário que uma clínica subiu no ProntuAI é um documento. Reenvio conta de novo: o mesmo prontuário mandado duas vezes são dois envios.",
      },
      {
        titulo: "Em que período cai",
        texto:
          "Pela data do envio. O período mais recente ainda está em andamento — no gráfico é o último ponto, e no card é a semana ou o mês corrente.",
      },
      {
        titulo: "A variação",
        texto:
          "Compara com o período anterior de mesmo tamanho: a semana anterior, o mês anterior, os três meses anteriores. Como o período atual ainda não acabou e o anterior está fechado, no começo da semana ou do mês a variação tende a sair negativa.",
      },
    ],
  },
  revisados: {
    titulo: "Análises realizadas",
    pergunta: "Quanto do que chegou já passou pela decisão do time BR MED.",
    blocos: [
      {
        titulo: "O que conta",
        texto:
          "Documento que uma pessoa do time BR MED — checador, gestor ou administrador — aprovou ou rejeitou. A decisão automática da IA não conta: documento aprovado pela IA e ainda não conferido fica fora.",
      },
      {
        titulo: "Em que período cai",
        texto:
          "Pela data em que o documento foi enviado, não pela data da revisão. Um prontuário enviado em 30/09 e revisado em 02/10 conta em setembro — por isso o número de um período continua crescendo depois que ele acaba.",
      },
      {
        titulo: "O percentual",
        texto:
          "Revisados ÷ enviados no mesmo período. Mostra quanto do volume a revisão humana já cobriu, não a velocidade dela.",
      },
    ],
  },
  pendentes: {
    titulo: "Análises pendentes",
    pergunta: "Quanto do que chegou ainda não passou pela decisão do time BR MED.",
    blocos: [
      {
        titulo: "O que conta",
        texto:
          "Envios realizados menos análises realizadas, no mesmo período: o prontuário que nenhuma pessoa do time BR MED aprovou ou rejeitou. São três situações: aprovado automaticamente (não faltou exame), erro no processamento (por exemplo, paciente não encontrado) e exame faltante apontado pela IA. Parte desses pedidos pode já ter sido liberada no BRNET.",
      },
      {
        titulo: "Em que período cai",
        texto:
          "Pela data do envio, como os outros dois cards. O número de um período diminui à medida que o time analisa os prontuários dele, mesmo depois que o período acaba. Por isso a variação tende a sair alta: o período atual ainda está em análise e o anterior já teve dias de revisão, então a comparação sobe mesmo com a fila igual.",
      },
      {
        titulo: "O subtítulo",
        texto:
          "Mostra quantos a IA marcou com exame faltante e quanto o total representa do que foi enviado. Exame faltante não é rejeitado automaticamente: o prontuário fica parado até alguém do time decidir.",
      },
    ],
  },
  expedicoes: {
    titulo: "Cobertura das expedições",
    pergunta: "De tudo o que a BR MED liberou nas credenciadas, quanto passou pelo ProntuAI. Meta: 100%.",
    blocos: [
      {
        titulo: "O total",
        texto:
          "Vem do BRNET (monitoramento de credenciados): todo pedido de credenciada liberado no período, datado pelo dia da liberação. Pedido atendido e ainda não liberado não entra.",
      },
      {
        titulo: "O que conta como via ProntuAI",
        texto:
          "O pedido que teve pelo menos um prontuário processado no ProntuAI, ligado pelo número do pedido no BRNET. Conta pedido, não documento, então reenvio não infla o número. Conta mesmo se o documento foi rejeitado: a pergunta é se a clínica usou a plataforma, não se o envio estava completo.",
      },
      {
        titulo: "Desde quando",
        texto:
          "A partir do mês em que os prontuários passaram a guardar o número do pedido do BRNET — antes disso não há como ligar um ao outro. Período que começa antes é medido a partir dessa data, e o card avisa. A conta para no último dia com documento no ProntuAI, para o total e a parte via ProntuAI cobrirem os mesmos dias.",
      },
      {
        titulo: "Cobertura das expedições",
        texto:
          "O gráfico faz essa conta em cada semana ou mês.",
      },
    ],
  },
  ranking: {
    titulo: "Ranking de clínicas",
    pergunta: "Quem mais mandou documentos no período.",
    blocos: [
      {
        titulo: "O que conta",
        texto:
          "Documentos enviados por clínica no período escolhido, do maior para o menor — a mesma conta de Envios realizados, aberta por clínica. Mostra as 6 maiores; o link abaixo abre todas. Cadastros de teste ficam fora.",
      },
      {
        titulo: "A variação",
        texto:
          "Contra o período anterior de mesmo tamanho. \"novo\" é clínica que não tinha enviado nada no período anterior. Passando o mouse, aparecem também quantos documentos dela já foram analisados pelo time e quantos estão aprovados.",
      },
    ],
  },
  prazoClinica: {
    titulo: "Envio da clínica × prazo do credenciado",
    pergunta: "A clínica manda o prontuário dentro do prazo dela?",
    blocos: [
      {
        titulo: "O prazo",
        texto:
          "A data prevista de liberação do pedido no BRNET: o dia do atendimento mais o prazo do credenciado, em dias úteis.",
      },
      {
        titulo: "A conta",
        texto:
          "Cada prontuário enviado é comparado com o prazo do seu pedido: antes do dia é antecipado, no próprio dia é no dia, depois é atrasado. O dia do envio é o do horário de Brasília — enviado às 22h do último dia ainda está no prazo.",
      },
      {
        titulo: "O que entra e quando",
        texto:
          "Conta cada envio, porque cada um foi uma entrega da clínica: reenvio do mesmo pedido entra de novo. Fica fora o documento sem número de pedido do BRNET ou cujo pedido não tem data prevista. Cai no período pelo dia do envio.",
      },
    ],
  },
  prazoTecnico: {
    titulo: "Liberação do técnico de credenciados × prazo da BR MED",
    pergunta: "O time BR MED libera dentro do prazo da BR MED?",
    blocos: [
      {
        titulo: "O prazo",
        texto:
          "A data de liberação que o BRNET devolve quando o ProntuAI processa o documento. Medido nos documentos, ela fica um dia útil depois do prazo da clínica — assim o técnico não é cobrado pelo dia que é da clínica.",
      },
      {
        titulo: "A conta",
        texto:
          "Só aprovações feitas por uma pessoa: o dia da aprovação contra o prazo, no horário de Brasília. Aprovação automática da IA e rejeições ficam fora. Cai no período pelo dia da aprovação.",
      },
    ],
  },
  usandoPouco: {
    titulo: "Quem está usando pouco",
    pergunta: "Das clínicas que já têm login no ProntuAI, quais deixam pedidos passarem por fora.",
    blocos: [
      {
        titulo: "Quem entra",
        texto:
          "Só as clínicas com login no ProntuAI (cadastro ativo). O BRNET não informa o cadastro, então a ligação é pelo nome do credenciado; quando o nome não bate, vale a clínica que enviou os documentos daquele credenciado, a partir de 3 documentos.",
      },
      {
        titulo: "Previstos na semana",
        texto:
          "Pedidos dessas clínicas no BRNET com previsão de liberação naquela semana, de segunda a domingo. Só semanas já fechadas.",
      },
      {
        titulo: "Os três desfechos",
        texto:
          "Cada previsto é acompanhado pelo número do pedido até o fim: Via ProntuAI (liberado, com prontuário processado na plataforma), Liberado por fora (liberado sem passar pela plataforma) ou Não liberado (ainda sem liberação no BRNET). Os três somam os previstos.",
      },
      {
        titulo: "Adesão",
        texto:
          "Via ProntuAI ÷ previstos da semana. Verde a partir de 90%, laranja de 75% a 90%, vermelho abaixo de 75%.",
      },
      {
        titulo: "Em que semana cai",
        texto:
          "Na semana da previsão, não na da liberação: pedido previsto para sexta e liberado na segunda conta na semana da sexta. Por isso uma semana fechada ainda muda — quando um pedido Não liberado sai, ele passa para um dos outros dois.",
      },
    ],
  },
  valeIncluir: {
    titulo: "Quem vale a pena incluir",
    pergunta: "Quais credenciadas ainda sem login no ProntuAI trariam mais volume.",
    blocos: [
      {
        titulo: "Quem entra",
        texto:
          "Credenciadas do BRNET sem cadastro ativo no ProntuAI que liberaram alguma coisa nas últimas 12 semanas ou têm pedido previsto na janela.",
      },
      {
        titulo: "Previstos",
        texto:
          "Pedidos ainda não liberados com previsão de hoje até o fim da janela: 7 dias no filtro Semana, 30 nos demais. É a ordem padrão da lista.",
      },
      {
        titulo: "Média por semana e semanas com liberação",
        texto:
          "A média soma as liberações das últimas 12 semanas fechadas e divide por 12, com as semanas zeradas na conta — sem os zeros, quem liberou 400 numa semana e nada nas outras onze pareceria liberar 400 por semana. A coluna ao lado diz em quantas dessas 12 semanas houve pelo menos uma liberação.",
      },
      {
        titulo: "PICO",
        texto:
          "Marca quem tem 5 ou mais previstos e mais que o dobro do que a média faria esperar no mesmo número de dias. Clicar no nome abre o histórico semana a semana, para conferir se é ritmo ou um evento isolado.",
      },
      {
        titulo: "Simulador",
        texto:
          "Soma a média semanal das clínicas marcadas e multiplica pela adesão da última semana fechada de Quem está usando pouco. O aumento é esse ganho sobre o volume que passou pela plataforma naquela mesma semana. O Top 5/10/20 pula as clínicas que recusaram, a menos que se marque para incluí-las. A simulação não grava nada.",
      },
      {
        titulo: "Abordagem",
        texto:
          "Em que pé está a conversa com cada clínica: Não abordada, Em contato, Aguardando retorno, Aceitou / em cadastro ou Recusou, que pede o motivo. Fica gravado na hora para todo o time, com quem mudou e quando; administradores e gestores alteram, os demais só veem. A lista filtra por status.",
      },
    ],
  },
  acuracia: {
    titulo: "Acurácia",
    pergunta: "Quantas vezes a IA e o revisor do time BR MED chegaram à mesma conclusão.",
    blocos: [
      {
        titulo: "Como a IA decide",
        texto:
          "A IA faz uma coisa só: confere se o prontuário tem todos os exames que a grade exige. A partir disso ela dá um de dois vereditos — aprova (libera o documento) ou rejeita (aponta o que falta e manda para a fila Pendentes, onde um checador decide).",
      },
      {
        titulo: "O que não entra na conta",
        texto:
          "Existe um terceiro desfecho que não é veredito: quando a IA não consegue nem ler o documento, porque não achou o CPF, o CNPJ veio errado ou o paciente não estava no BRNET. Isso é falha técnica de leitura, não julgamento. Fica fora da acurácia e é acompanhado à parte — seria como reprovar um revisor por causa de uma folha que chegou rasgada.",
      },
      {
        titulo: "O que é acurácia aqui",
        texto:
          "Acurácia é concordância direta: quantas vezes a IA e o revisor humano chegaram à mesma conclusão. Conta como acerto quando a IA aprovou e o humano confirmou, e quando a IA rejeitou e o humano confirmou a rejeição.",
      },
      {
        titulo: "A exceção: motivo externo",
        texto:
          "Nem toda divergência é erro da IA. Às vezes o revisor contraria a IA por uma razão que estava fora do documento — o exame chegou por outro canal, o paciente já tinha o resultado no sistema, a clínica confirmou por fora. Nesses casos a leitura da IA estava certa para o que ela tinha em mãos, e o caso conta como acerto. Quem diz isso é o revisor: ao liberar o que a IA rejeitou, ele marca no parecer que ela acertou e escolhe o motivo. Antes do parecer, o motivo era reconhecido pelo texto da justificativa.",
      },
      {
        titulo: "Onde mora o risco",
        texto:
          "O motivo externo aparece muito mais de um lado que do outro. Quando a IA rejeita e o humano libera, um terço das vezes é motivo externo. Mas quando a IA aprova e o humano derruba, quase nunca é — nesses casos a IA errou de verdade, e é aí que existe o risco de um documento incompleto passar batido.",
      },
      {
        titulo: "Quais documentos entram",
        texto:
          "Os que tiveram veredito da IA e, depois, decisão de uma pessoa do time BR MED. O mesmo arquivo reenviado conta uma vez só — fica o primeiro envio, que é onde a IA decidiu sem saber de nada. Cai no período pela data do envio, não da revisão.",
      },
      {
        titulo: "Acurácia por período",
        texto:
          "O gráfico faz a mesma conta em cada semana ou mês. A escala começa em 70% para as diferenças entre os pontos aparecerem.",
      },
    ],
  },
  concordancia: {
    titulo: "Concordância direta",
    pergunta: "A acurácia sem a exceção do motivo externo.",
    blocos: [
      {
        titulo: "A conta",
        texto:
          "IA aprovou e o revisor aprovou, mais IA apontou falta e o revisor rejeitou, sobre a mesma base da acurácia. A única diferença para a acurácia é que aqui a divergência resolvida por motivo externo não conta como acerto.",
      },
      {
        titulo: "Como ler junto com a acurácia",
        texto:
          "A distância entre os dois números é o peso do motivo externo no período. Se ela cresce, mais divergências estão sendo explicadas por razão de fora do documento.",
      },
    ],
  },
  derrubadas: {
    titulo: "Aprovações derrubadas",
    pergunta: "Quantas vezes a IA liberou um documento que o revisor barrou.",
    blocos: [
      {
        titulo: "A conta",
        texto:
          "Documentos que a IA aprovou e uma pessoa do time BR MED rejeitou, tirando os casos em que o revisor registrou motivo externo. É número absoluto, não percentual.",
      },
      {
        titulo: "Por que importa",
        texto:
          "É o erro com consequência: sem a revisão humana, o documento incompleto teria passado. Aqui a variação para baixo é a boa.",
      },
    ],
  },
  falhas: {
    titulo: "Falhas técnicas",
    pergunta: "Quantas vezes a IA não chegou a julgar o documento.",
    blocos: [
      {
        titulo: "A conta",
        texto:
          "Documentos em que a IA parou antes de olhar os exames — não achou o CPF, o CNPJ veio errado, o paciente não estava no BRNET, entre outros impedimentos — e que depois tiveram decisão de uma pessoa do time BR MED. Falha que ainda está na fila não aparece aqui.",
      },
      {
        titulo: "Por que fica fora da acurácia",
        texto:
          "Não houve veredito para comparar com o do revisor. O número é acompanhado à parte, como medida da leitura dos documentos. A variação para baixo é a boa.",
      },
      {
        titulo: "O que não conta como falha",
        texto:
          "Quando o revisor libera e marca no parecer que o CNPJ do ASO é de outra empresa, ou que o atendimento ainda não estava registrado no BRNET, a IA não falhou: leu certo, e o dado de fora é que não batia. Esses casos saem do número.",
      },
    ],
  },
  motivos: {
    titulo: "Por que a acurácia não está maior",
    pergunta: "Do que são feitas as divergências que contam contra a IA.",
    blocos: [
      {
        titulo: "O que entra",
        texto:
          "Só as divergências que derrubam a acurácia: a IA aprovou e o revisor rejeitou, ou a IA apontou falta e o revisor liberou. Motivo externo e falha técnica ficam fora.",
      },
      {
        titulo: "Resolvidas por motivo externo",
        texto:
          "Abaixo das barras, as divergências em que o revisor marcou no parecer que a decisão mudou por algo fora do documento — exame feito em outro sistema, voucher não anexado, CNPJ de outra empresa, atendimento ainda fora do BRNET, duplicidade, autorização do cliente. Contam como acerto, por isso não estão nas barras. \"Justificativa escrita antes do modal\" é o histórico reconhecido por palavra-chave.",
      },
      {
        titulo: "Como cada uma é classificada",
        texto:
          "Pelo parecer do modal de feedback, quando há: o revisor diz, exame a exame, onde a IA errou. Sem parecer, como em todo o histórico anterior a 19/10, pelo texto que o revisor escreveu ao decidir, por palavras-chave. Exame faltante que a IA não detectou: a IA aprovou e o revisor apontou um exame que não estava. IA não reconheceu exame que estava no PDF: a IA apontou falta e o revisor disse que o exame estava lá. Regra formal que a IA ainda não verifica: carimbo, assinatura, aptidão, data, legibilidade, documento de outra pessoa ou exigido pela empresa. Revisor não informou a causa: sem parecer e com justificativa vazia ou só \"ok\". Outros motivos: o que sobra.",
      },
      {
        titulo: "Por que \"a confirmar\"",
        texto:
          "Sem parecer, a classificação lê texto livre, e parte dos casos cai na categoria errada. Ela explica a divergência, não decide se houve: mexer nela não move a acurácia.",
      },
    ],
  },
  matriz: {
    titulo: "Matriz de decisão",
    pergunta: "Todos os desfechos possíveis entre a IA e o revisor.",
    blocos: [
      {
        titulo: "As cinco linhas",
        texto:
          "Os dois acertos diretos (a IA aprovou e o humano aprovou; a IA apontou falta e o humano rejeitou), a divergência resolvida por motivo externo, que também conta como acerto, e as duas divergências: a IA apontou falta e o humano liberou, e a IA aprovou e o humano rejeitou — esta é o risco real.",
      },
      {
        titulo: "O percentual",
        texto:
          "Cada linha sobre a base da acurácia, então as cinco somam 100% e as três de acerto somam a acurácia do período. Falhas técnicas ficam fora da matriz.",
      },
    ],
  },
  acuraciaExame: {
    titulo: "Acurácia por exame",
    pergunta: "Em quais exames o processo tem mais dificuldade, e por quê, segundo o revisor.",
    blocos: [
      {
        titulo: "De onde vem",
        texto:
          "Do parecer que o revisor dá no modal de feedback da Checagem. Para cada exame, ele diz se a IA acertou e, quando não, o motivo. É ele quem diz, exame a exame — nada é deduzido da decisão sobre o documento.",
      },
      {
        titulo: "A conta",
        texto:
          "Na lista, \"Documentos\" é em quantos documentos com parecer o exame era exigido pelo BRNET — ou foi digitado pelo revisor (\"Estava, mas não foi lido\"). É erro quando o revisor marcou qualquer motivo no exame. Acurácia = documentos sem erro ÷ documentos, somando todos os exames.",
      },
      {
        titulo: "Os motivos",
        texto:
          "Clique no nome do exame para ver os motivos, com as palavras que o revisor marcou no modal, e os documentos em que o erro aconteceu, com o link para abrir cada um. Todos os motivos baixam a acurácia, inclusive os que a IA ainda não confere (outra data, ilegível, sem carimbo) e a exigência errada do BRNET.",
      },
      {
        titulo: "O que fica de fora",
        texto:
          "O documento em que a IA não chegou a julgar os exames (falha técnica) e os problemas do documento inteiro, como nome ou CPF lidos errado — esses não têm exame.",
      },
      {
        titulo: "A amostra",
        texto:
          "Só entram documentos com parecer. Por isso a adesão aparece junto: pareceres sobre as decisões do time BR MED desde que o modal existe. Com poucos pareceres o número pesa pouco. E o \"Acertou\" já vem marcado quando a IA e o revisor decidem igual, o que pode esconder parte dos erros.",
      },
      {
        titulo: "Em que período cai",
        texto:
          "Pela data de envio do documento, como a acurácia geral, e segue o filtro de período. A lista vai da menor acurácia para a maior; no empate, o que tem mais erros primeiro. Exame com menos de 5 avaliações no período não ganha percentual — um erro sozinho o derrubaria: com erro, aparece em \"Poucos casos\", só com a contagem; sem erro, entra só no total.",
      },
    ],
  },
};

/** Qual entrada de `COMO_CALCULAMOS` cada KPI abre — pelo rótulo, como as dicas. */
const AJUDA_KPI: Record<string, IdIndicador> = {
  "Envios realizados": "enviados",
  "Análises realizadas": "revisados",
  "Análises pendentes": "pendentes",
  Acurácia: "acuracia",
  "Concordância direta": "concordancia",
  "Aprovações derrubadas": "derrubadas",
  "Falhas técnicas": "falhas",
  "Acurácia por exame": "acuraciaExame",
};

// ── formatação e datas ───────────────────────────────────────────────────────
const MESES_ABBR = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"];

const pad = (n: number) => String(n).padStart(2, "0");

// Sem `split`/`map`: a chave é sempre ISO com zero à esquerda, e esta função é
// chamada dezenas de milhares de vezes por recálculo — o array intermediário
// custava mais que a conta.
const partes = (chave: string) => ({
  y: Number(chave.slice(0, 4)),
  m: Number(chave.slice(5, 7)),
  d: Number(chave.slice(8, 10)),
});

// "2026-09-29" -> "29/09", recortando a string. A chave ISO já vem com dois
// dígitos em cada campo, então não há o que formatar.
const rotuloSemana = (chave: string) => `${chave.slice(8, 10)}/${chave.slice(5, 7)}`;

const isoUTC = (d: Date) =>
  `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;

/** Dia ISO deslocado em `dias`. */
const maisDias = (iso: string, dias: number) => {
  const { y, m, d } = partes(iso);
  return isoUTC(new Date(Date.UTC(y, m - 1, d + dias)));
};

/**
 * Segunda-feira da semana ISO de uma data. A mesma chave que o back-end usa em
 * `desfecho_previsao_semana` e `liberacoes_semana` — as duas pontas precisam
 * concordar sobre onde a semana começa, ou a tela soma caixas diferentes.
 */
const semanaDe = (iso: string) => {
  const { y, m, d } = partes(iso);
  const dt = new Date(Date.UTC(y, m - 1, d));
  return isoUTC(new Date(Date.UTC(y, m - 1, d - ((dt.getUTCDay() + 6) % 7))));
};

/**
 * "29/09 a 05/10" — a semana inteira, não só o dia em que ela começa.
 *
 * Memoizado: existem algumas dezenas de semanas distintas, e o rótulo de cada
 * uma era refeito uma vez por clínica — centenas de vezes a mesma string, cada
 * uma com uma data nova por trás.
 */
const _intervalos = new Map<string, string>();
const intervaloSemana = (inicioISO: string) => {
  const pronto = _intervalos.get(inicioISO);
  if (pronto !== undefined) return pronto;
  const rotulo = `${rotuloSemana(inicioISO)} a ${rotuloSemana(maisDias(inicioISO, 6))}`;
  _intervalos.set(inicioISO, rotulo);
  return rotulo;
};

const rotuloMes = (chave: string) => {
  const { y, m } = partes(chave);
  return `${MESES_ABBR[m - 1]}/${String(y).slice(2)}`;
};

// Os formatadores são instanciados UMA vez, não a cada número.
// `v.toLocaleString("pt-BR", {...})` constrói um `Intl.NumberFormat` por
// chamada, e isso domina o custo de recalcular a visão: medido em 30% do tempo
// total, só nestas duas funções. Com a instância reaproveitada, a troca de
// período deixa de travar a tela.
const NUM_INTEIRO = new Intl.NumberFormat("pt-BR");
const NUM_UMA_CASA = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const fmt = (v: number) => NUM_INTEIRO.format(v);
/** Uma casa decimal. A média semanal quase nunca é inteira, e "16,333" polui. */
const umDecimal = (v: number) => NUM_UMA_CASA.format(v);
const num = (v: number) => `${v.toFixed(1).replace(".", ",")}%`;
const pct = (a: number, b: number) => (b ? (a / b) * 100 : 0);

/** Variação em pontos percentuais entre duas taxas. */
const pp = (atualPct: number, antPct: number | null) =>
  antPct === null
    ? ""
    : `${atualPct >= antPct ? "+" : "-"}${Math.abs(atualPct - antPct).toFixed(1).replace(".", ",")} p.p.`;

/** Nome do período coberto por um conjunto de pontos. */
function nomePeriodo(serie: SerieKey, pontos: { chave: string }[]) {
  if (!pontos.length) return "sem dados";
  if (serie === "semanal") {
    return pontos.length === 1
      ? `semana de ${rotuloSemana(pontos[0].chave)}`
      : `${rotuloSemana(pontos[0].chave)} – ${rotuloSemana(pontos[pontos.length - 1].chave)}`;
  }
  const a = rotuloMes(pontos[0].chave);
  const b = rotuloMes(pontos[pontos.length - 1].chave);
  return a === b ? a : `${a} – ${b}`;
}

/**
 * Quantas expedições credenciadas houve entre duas datas, somando os dias.
 * `ultimoDia` é a data mais recente com dado do ProntuAI: nada além dela entra,
 * para que numerador e denominador cubram exatamente a mesma janela.
 */
function expedicoesEntre(
  porDia: Record<string, number>,
  ini: Date,
  fim: Date,
  ultimoDia: Date | null,
) {
  let total = 0;
  const d = new Date(ini.getTime());
  const limite = ultimoDia && fim > ultimoDia ? ultimoDia : fim;
  while (d <= limite) {
    const chave = `${pad(d.getUTCFullYear())}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
    total += porDia[chave] || 0;
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return Math.round(total);
}

/** Soma [antecipado, no dia, atrasado] dos dias entre `ini` e `fim`. */
function prazosEntre(porDia: Record<string, Prazos>, ini: Date, fim: Date): Prazos {
  const total: Prazos = [0, 0, 0];
  const d = new Date(ini.getTime());
  while (d <= fim) {
    const dia = porDia[`${pad(d.getUTCFullYear())}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`];
    if (dia) for (let i = 0; i < 3; i++) total[i] += dia[i] || 0;
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return total;
}

/**
 * Soma os pontos de uma clínica que caem no período. As chaves das séries por
 * clínica são as mesmas da série geral, então o casamento é exato.
 */
function acumular(clinica: ClinicaDados, pontos: PontoSerie[], serieKey: SerieKey) {
  const serie = clinica.series?.[serieKey] || {};
  return pontos.reduce(
    (acc, p) => {
      const x = serie[p.chave];
      if (x) {
        acc.docs += x.docs;
        acc.revisados += x.revisados;
        acc.validados += x.validados;
      }
      return acc;
    },
    { docs: 0, revisados: 0, validados: 0 },
  );
}

// ── shape da visão ───────────────────────────────────────────────────────────
export interface Kpi {
  label: string;
  value: string;
  sub: string;
  tip: string;
  delta: string;
  deltaColor: string;
  /** Entrada de `COMO_CALCULAMOS` que o "?" do card abre. */
  ajuda?: IdIndicador;
}

export interface BarraDocs {
  month: string;
  value: number;
  h: number;
  tip: string;
}

export interface BarraPercentual {
  month: string;
  label: string;
  h: number;
  tip: string;
}

export interface BarraExpedicao {
  month: string;
  total: string;
  hAnt: number;
  hDia: number;
  hAtr: number;
  tip: string;
}

/** Um dos dois gráficos de prazo — clínica ou técnico de credenciados. */
export interface GraficoPrazo {
  barras: BarraExpedicao[];
  /** "93% antecipados ou no dia", na janela do gráfico. */
  resumo: string;
}

export interface LinhaRanking {
  name: string;
  docs: number;
  pct: number;
  color: string;
  delta: string;
  deltaColor: string;
  tip: string;
}

/**
 * Uma linha de "Quem está usando pouco": uma clínica habilitada numa semana
 * fechada. Os três desfechos somam `previstos`, então a barra fecha em 100%.
 *
 * Aqui previsto e realizado se encontram — e só aqui. Não é agregado dividido
 * por agregado: o back-end acompanha o MESMO pedido, pelo id, da previsão até o
 * desfecho. É o que a `LinhaAdesao` não conseguia fazer, e é por isso que ela
 * misturava uma janela para frente com outra para trás na mesma linha.
 */
export interface LinhaUsoSemana {
  clinica: string;
  local: string;
  /** Pedidos com previsão de liberação nesta semana. É o denominador. */
  previstos: number;
  /** Liberados e com documento no ProntuAI. */
  viaProntuai: number;
  /** Liberados sem passar pela plataforma — o buraco que é com quem cuida de adesão. */
  fora: number;
  /** Nem liberados até agora — o buraco que é atraso do credenciado. */
  naoLiberado: number;
  /** viaProntuai ÷ previstos, em %. */
  adesao: number;
  adesaoLabel: string;
  adesaoColor: string;
  /** Larguras da barra empilhada, em % dos previstos. */
  pctVia: number;
  pctFora: number;
  pctNao: number;
  tip: string;
}

/** Uma semana fechada, com as clínicas que tinham previsão nela. */
export interface SemanaUso {
  /** Segunda-feira da semana ISO. */
  iso: string;
  /** "29/09 a 05/10". */
  label: string;
  linhas: LinhaUsoSemana[];
  previstos: number;
  viaProntuai: number;
  fora: number;
  naoLiberado: number;
  /** Ponderada: viaProntuai ÷ previstos da semana inteira. */
  adesao: number;
  adesaoLabel: string;
}

/**
 * Indicador "Quem está usando pouco". Só semanas FECHADAS: a adesão precisa do
 * desfecho para existir, e semana em curso ainda tem pedido no prazo.
 *
 * Só semanas a partir de `expedicoes_desde`, também: antes dela o documento não
 * guardava `pedido_exame_id`, então "passou pelo ProntuAI" daria zero para todo
 * mundo e a tela acusaria uma debandada que nunca houve.
 */
export interface UsoSemanal {
  /** Da mais recente para a mais antiga. */
  semanas: SemanaUso[];
}

/** Um dia da lista de previsões do modal. */
export interface DataPrevista {
  label: string;
  pedidos: string;
  /** O mesmo `pedidos`, numérico, para a barra da lista. */
  n: number;
}

/** Uma coluna do histórico semanal do modal. */
export interface BarraSemana {
  /** Segunda-feira da semana, ISO. */
  iso: string;
  /** "29/09". */
  label: string;
  liberacoes: number;
  /**
   * Semana que destoa do comportamento dela: mais que o dobro da média e pelo
   * menos 3 liberações acima. As duas condições juntas porque só a razão marca
   * ruído (1 → 3 é "três vezes mais" e não quer dizer nada) e só a diferença
   * marca a clínica grande, onde oscilar 5 é rotina.
   */
  pico: boolean;
  /** Uma das semanas fechadas que entram na média. */
  naMedia: boolean;
  /** Semana corrente: ainda não acabou, e o número só pode subir. */
  parcial: boolean;
  tip: string;
}

/**
 * Uma linha de "Quem vale a pena incluir": um credenciado SEM cadastro no
 * ProntuAI. Nenhuma métrica de adesão entra aqui — adesão é sobre quem já está
 * dentro, e misturar as duas foi o que fez quatro indicadores contarem a mesma
 * história.
 *
 * O ranking é pela MÉDIA semanal de liberações. Previsto da janela não serve de
 * ordem: é uma foto do instante e premia duas coisas erradas — o pico isolado
 * ("mil na semana que vem") e o credenciado lento, único que tem pedido pendente
 * na hora do cálculo.
 *
 * Média, e não mediana, por decisão de produto (14/10/2026). A mediana derruba
 * sozinha a clínica de pico único; a média não, então quem denuncia o pico é o
 * gráfico do modal e a marca de PICO — que é exatamente o fluxo pedido:
 * ranquear, desconfiar, clicar e conferir.
 */
export interface LinhaForaProntuai {
  /** Rótulo completo do BRNET, mostrado ao expandir. */
  credenciado: string;
  name: string;
  local: string;
  /** Média de liberações por semana nas últimas semanas fechadas. */
  media: number;
  mediaLabel: string;
  /** Liberações somadas na mesma janela da média. */
  total: number;
  /** Semanas com ao menos uma liberação, na janela da média. */
  semanasAtivas: number;
  /** semanasAtivas ÷ semanas da janela, em %. */
  regularidade: number;
  regularidadeLabel: string;
  /** Largura da barra do ranking, em % da maior média da lista. */
  pct: number;
  /** Pedidos previstos na janela para frente — coluna de contexto, não de ordem. */
  previstos: number;
  /**
   * Os previstos da janela destoam do ritmo dela: mais que o dobro do que a
   * média faria esperar no mesmo número de dias. É o "boom momentâneo".
   */
  picoPrevisto: boolean;
  /** O que a média faria esperar nos mesmos dias da janela de previstos. */
  esperado: number;
  esperadoLabel: string;
  /**
   * Histórico semanal inteiro, para o modal. Uma coluna por semana, inclusive
   * as zeradas, e o mesmo intervalo para todo credenciado.
   *
   * Função, e não lista, porque só o modal lê — uma clínica por vez. Montar as
   * ~350 × 46 colunas a cada troca de filtro dobrava o custo do recálculo
   * (medido: 15 → 29 ms), e era exatamente o travamento recém-corrigido.
   */
  serie: () => BarraSemana[];
  /** Primeira data prevista, "—" quando não há nenhuma. */
  proxima: string;
  /** ISO da próxima previsão, para ordenar por data e não por texto. */
  proximaISO: string;
  datas: DataPrevista[];
  /** Pendentes com a previsão já vencida. */
  vencidos: number;
  /** Previstos para depois do fim da janela. */
  depoisDaJanela: number;
  /** Documentos que o credenciado já mandou pelo ProntuAI, em todo o histórico. */
  documentos: number;
  tip: string;
}

/** Um motivo de erro de um exame, com as palavras que o revisor clicou no modal. */
export interface MotivoErroExame {
  rotulo: string;
  /** O que a IA tinha dito do exame quando o revisor marcou isso. */
  contexto: string;
  casos: number;
}

/** Um documento em que o exame deu erro — a linha que leva ao PDF. */
export interface CasoErroExameVisao {
  documento: string;
  clinica: string;
  enviadoLabel: string;
  motivo: string;
}

/** Uma linha da lista de "Acurácia por exame" (modal aberto pelo número do card). */
export interface LinhaAcuraciaExame {
  exame: string;
  /** Documentos com parecer em que o exame era exigido (ou foi apontado). */
  documentos: number;
  erros: number;
  /** Largura da barra de erro, em % da linha. */
  pctErro: number;
  /** Do motivo mais frequente ao menos; aberto ao clicar no exame. */
  motivos: MotivoErroExame[];
  /** Mais recente primeiro. */
  casos: CasoErroExameVisao[];
  acuracia: number;
  acuraciaLabel: string;
  tip: string;
}

/** "Acurácia por exame", do parecer do modal de feedback, no período escolhido. */
export interface AcuraciaExameVisao {
  kpi: Kpi;
  /** Exames com pelo menos `minimo` documentos. */
  linhas: LinhaAcuraciaExame[];
  /** Abaixo do mínimo, mas com erro: aparecem à parte, sem percentual. */
  poucosCasos: LinhaAcuraciaExame[];
  minimo: number;
  /** Exames abaixo do mínimo e sem erro: entram no total, não na lista. */
  abaixoDoMinimo: number;
  /** Soma, por exame, dos documentos em que ele era exigido — a base da acurácia. */
  avaliacoes: number;
  erros: number;
  pareceres: number;
  decisoes: number;
  /** Pareceres ÷ decisões; null sem decisão no período. */
  adesaoLabel: string | null;
  acuraciaLabel: string;
  periodoLabel: string;
}

export interface LinhaMatriz {
  name: string;
  vol: string;
  acc: string;
  classificacao: string;
  classificacaoColor: string;
  peso: number;
  cor: string;
}

export interface FatorPenteFino {
  name: string;
  count: number;
  color: string;
  pct: number;
  tip: string;
}

export interface VisaoDashboard {
  rangeLabel: string;
  compareLabel: string;
  chipPeriodo: string;
  graficoLegenda: string;

  kpiPrimary: Kpi[];
  docsSeries: BarraDocs[];
  coberturaSeries: BarraPercentual[];
  prazoClinica: GraficoPrazo;
  prazoTecnico: GraficoPrazo;
  ranking: LinhaRanking[];
  totalClinicas: number;
  /**
   * "Quem está usando pouco": adesão por clínica habilitada, semana a semana.
   * Substituiu a tabela de adesão, o card de projeção e a tabela de
   * oportunidade — as três liam os mesmos previstos e contavam pedaços da mesma
   * história, cada uma com uma janela diferente.
   */
  usoSemanal: UsoSemanal | null;
  /**
   * "Quem vale a pena incluir": credenciados fora do ProntuAI, ranqueados pela
   * média semanal. Substituiu o card de previstos, a comparação dentro × fora
   * e a lista de prioridade ordenada por previstos. null sem o BRNET.
   */
  foraProntuai: LinhaForaProntuai[] | null;
  /** Janela para frente dos previstos: "de hoje a 12/11 · 30 dias". */
  janelaPrevistos: string;
  /** Intervalo das semanas da média: "27/07 a 05/10". */
  janelaMedia: string;
  /**
   * Insumos do simulador. Ele não recalcula nada do painel: parte do volume
   * semanal que hoje passa pela plataforma e aplica, sobre a média das
   * clínicas marcadas, a adesão medida na última semana fechada.
   */
  simulador: { viaProntuaiSemana: number; adesao: number; semana: string } | null;
  /** Rótulo do filtro de período, para os blocos retroativos se situarem. */
  periodoLabel: string;

  kpisAcuracia: Kpi[];
  acuraciaSeries: BarraPercentual[];
  fatorPrincipal: string;
  penteFino: FatorPenteFino[];
  /** Divergências resolvidas por motivo externo, por motivo, maior primeiro. */
  motivosExternos: { name: string; count: number }[];
  motivosExternosTotal: number;
  notaSemJustificativa: string;
  porTipo: LinhaMatriz[];
  /**
   * null num back-end sem o indicador (o card mostra "Em breve"). Com o
   * indicador e sem parecer no período, vem com zeros e o card mostra "—".
   */
  acuraciaExame: AcuraciaExameVisao | null;
}

export interface OpcoesVisao {
  dados: DadosDashboard;
  filtro: FiltroPeriodo;
  comparar: boolean;
  verTodasClinicas: boolean;
}

/**
 * "Acurácia por exame": exame com menos avaliações que isto no período não ganha
 * percentual — com poucos casos, um erro sozinho o derrubaria. Se teve erro, vai
 * para "Poucos casos", só com a contagem; se não teve, entra só no total.
 */
const MINIMO_AVALIACOES_EXAME = 5;

// O motivo com as palavras do modal de feedback (`CATEGORIAS_EXAME`) e, ao lado, o
// que a IA tinha dito do exame — a opção só aparece ao revisor naquela situação
// (`OPCOES_EXAME`): "Não estava" sozinho não diz que a IA deu o exame como achado.
const CONTEXTO_OPCAO: Record<keyof typeof OPCOES_EXAME, string> = {
  faltante: "a IA apontou falta",
  encontrado: "a IA deu como encontrado",
  avulso: "fora da lista do BRNET",
};
const ROTULO_MOTIVO: Record<string, string> = Object.fromEntries(CATEGORIAS_EXAME.map((c) => [c.valor, c.rotulo]));
const CONTEXTO_MOTIVO: Record<string, string> = {};
for (const [situacao, opcoes] of Object.entries(OPCOES_EXAME) as [keyof typeof OPCOES_EXAME, { categoria: string }[]][]) {
  for (const o of opcoes) CONTEXTO_MOTIVO[o.categoria] ??= CONTEXTO_OPCAO[situacao];
}

/** Escala do gráfico de acurácia: a métrica vive na faixa alta e 0–100 achataria. */
const PISO_ACC = 70;

const DIAS_ABBR = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];

export function calcularVisao({ dados, filtro, comparar, verTodasClinicas }: OpcoesVisao): VisaoDashboard {
  const cfg = PERIODOS[filtro] ?? PERIODOS.Mensal;

  // ---- período dos indicadores ---------------------------------------------
  const serieP = dados.series?.[cfg.periodo.serie] ?? [];
  const np = cfg.periodo.n;
  const atual = np ? serieP.slice(-np) : serieP.slice();
  const anterior = np
    ? serieP.slice(Math.max(0, serieP.length - 2 * np), Math.max(0, serieP.length - np))
    : [];
  // Só compara blocos de mesmo tamanho — período anterior parcial distorceria.
  const comparavel = np > 0 && atual.length === np && anterior.length === np;

  // ---- série de contexto dos gráficos --------------------------------------
  const serieG = dados.series?.[cfg.grafico.serie] ?? [];
  const grafico = cfg.grafico.n ? serieG.slice(-cfg.grafico.n) : serieG.slice();
  const rotuloG = cfg.grafico.serie === "semanal" ? rotuloSemana : rotuloMes;

  const soma = <T,>(arr: T[], campo: keyof T) =>
    arr.reduce((acc, p) => acc + (Number(p[campo]) || 0), 0);

  const delta = (v: string, dir: "up" | "down") => {
    const good = dir !== "down";
    if (!v) return { delta: "", deltaColor: MUTED };
    if (!comparar) return { delta: "—", deltaColor: MUTED };
    const neg = v.startsWith("-");
    // A seta já diz a direção; o número vai sem sinal, nos dois sentidos.
    return {
      delta: `${neg ? "▾" : "▴"} ${v.replace(/^[+-]/, "")}`,
      deltaColor: neg === !good ? POS : NEG,
    };
  };

  const kpi = (label: string, value: string, d: string, dir: "up" | "down", sub?: string): Kpi => ({
    label,
    value,
    sub: sub || "",
    tip: TIPS_KPI[label] || "",
    ajuda: AJUDA_KPI[label],
    ...delta(d, dir),
  });

  const kpiAcc = (label: string, value: string, d: string, dir: "up" | "down", sub?: string): Kpi => ({
    ...kpi(label, value, d, dir, sub),
    tip: TIPS_ACC[label] || "",
  });

  const variacao = (campo: keyof PontoSerie) => {
    if (!comparavel) return "";
    const a = soma(atual, campo);
    const b = soma(anterior, campo);
    if (!b) return a ? "novo" : "";
    return `${a >= b ? "+" : "-"}${Math.abs(((a - b) / b) * 100).toFixed(0)}%`;
  };

  const enviados = soma(atual, "docs");
  const revisados = soma(atual, "revisados");
  // Envio que nenhuma pessoa do time aprovou ou rejeitou, decidido ou não pela IA.
  const pendentes = Math.max(0, enviados - revisados);
  // Status "pending" é o que a IA processou e marcou com exame faltante: ela
  // não rejeita sozinha por isso, e o prontuário espera o time.
  const comFaltante = soma(atual, "pendentes");
  const variacaoPendentes = () => {
    if (!comparavel) return "";
    const b = soma(anterior, "docs") - soma(anterior, "revisados");
    if (!b) return pendentes ? "novo" : "";
    return `${pendentes >= b ? "+" : "-"}${Math.abs(((pendentes - b) / b) * 100).toFixed(0)}%`;
  };

  const bar = (v: number, max: number, h: number) => (v <= 0 ? 0 : Math.max(3, Math.round((v / max) * h)));
  const maxDocs = Math.max(1, ...grafico.map((p) => p.docs));

  /** Primeiro e último dia de um ponto do gráfico (semana ou mês). */
  const faixaDoPonto = (chave: string) => {
    const a = partes(chave);
    const ini = new Date(Date.UTC(a.y, a.m - 1, a.d));
    const fim =
      cfg.grafico.serie === "semanal"
        ? new Date(Date.UTC(a.y, a.m - 1, a.d + 6))
        : new Date(Date.UTC(a.y, a.m, 0));
    return { ini, fim };
  };

  const graficoPrazo = (porDia: Record<string, Prazos>, noun: [string, string]): GraficoPrazo => {
    const [sing, plur] = noun;
    const pontos = grafico.map((p) => {
      const { ini, fim } = faixaDoPonto(p.chave);
      return { chave: p.chave, v: prazosEntre(porDia, ini, fim) };
    });
    const maxP = Math.max(1, ...pontos.map(({ v }) => v[0] + v[1] + v[2]));
    const soma: Prazos = [0, 0, 0];
    pontos.forEach(({ v }) => v.forEach((n, i) => (soma[i] += n)));
    const tot = soma[0] + soma[1] + soma[2];
    const q = (n: number) => `${fmt(n)} ${n === 1 ? sing : plur}`;
    return {
      resumo: tot ? `${num(pct(soma[0] + soma[1], tot))} antecipados ou no dia · ${q(tot)}` : "",
      barras: pontos.map(({ chave, v: [ant, dia, atr] }) => {
        const t = ant + dia + atr;
        return {
          month: rotuloG(chave),
          total: t ? fmt(t) : "—",
          hAnt: bar(ant, maxP, 190),
          hDia: bar(dia, maxP, 190),
          hAtr: bar(atr, maxP, 190),
          tip: t
            ? `${rotuloG(chave)} — ${fmt(ant)} antecipados, ${fmt(dia)} no dia, ${fmt(atr)} atrasados (${num(pct(atr, t))} atrasados)`
            : `${rotuloG(chave)} — sem ${plur} com previsão`,
        };
      }),
    };
  };

  // ---- cobertura: pedidos do BRNET com documento liberado no ProntuAI --------
  // Numerador e denominador contam pedidos, pelo dia de LIBERAÇÃO — realizado
  // é pedido expedido, não atendido (definição da 1.2).
  const porDia = dados.expedicoes_dia || {};
  const viaPorDia = dados.expedicoes_prontuai_dia || {};
  const dataDe = (iso?: string) => {
    if (!iso) return null;
    const q = partes(iso);
    return new Date(Date.UTC(q.y, q.m - 1, q.d));
  };
  const primeiroDoc = dataDe(dados.periodo?.doc_mais_antigo);
  const ultimoDoc = dataDe(dados.periodo?.doc_mais_recente);
  // A ligação documento↔pedido só existe a partir de `expedicoes_desde` (jun/26).
  // Sem ela não há cobertura medível: o denominador vira 0 e o KPI cai no absoluto.
  const desde = dataDe(dados.expedicoes_desde ?? undefined);
  const inicioCobertura = desde && (!primeiroDoc || desde > primeiroDoc) ? desde : primeiroDoc;
  const expedicoesEmpresa = (ini: Date, fim: Date) =>
    desde ? expedicoesEntre(porDia, ini, fim, ultimoDoc) : 0;

  // ---- credenciados sem ProntuAI: datas previstas ---------------------------
  // "hoje" vem do back-end (quando a consulta rodou), não do relógio do browser:
  // o painel é recalculado uma vez por dia e o fuso do servidor é quem manda.
  const hojeISO = (dados.gerado_em ?? "").slice(0, 10);
  const amanhaISO = (() => {
    if (!hojeISO) return "";
    const q = partes(hojeISO);
    const d = new Date(Date.UTC(q.y, q.m - 1, q.d + 1));
    return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
  })();
  // Janela para frente do card de previstos: de hoje até hoje + (dias - 1), com
  // o dia de hoje incluído. Sem `gerado_em` não há "hoje" confiável — o relógio
  // do browser não serve, porque o painel é calculado uma vez por dia no fuso do
  // servidor —, então o recorte é desligado em vez de sair errado.
  const diasJanela = JANELA_PREVISTOS[filtro] ?? JANELA_PREVISTOS.Mensal;
  const fimJanelaISO = (() => {
    if (!hojeISO) return "";
    const q = partes(hojeISO);
    const d = new Date(Date.UTC(q.y, q.m - 1, q.d + diasJanela - 1));
    return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
  })();
  const temJanela = !!hojeISO;

  const dataCurta = rotuloSemana;

  // No painel expandido o dia da semana importa: é o que responde "isso é pra
  // semana que vem?" sem a pessoa ter que consultar o calendário.
  const rotuloPrevisao = (iso: string) => {
    const q = partes(iso);
    const data = `${pad(q.d)}/${pad(q.m)}`;
    if (iso === hojeISO) return `hoje, ${data}`;
    if (iso === amanhaISO) return `amanhã, ${data}`;
    return `${DIAS_ABBR[new Date(Date.UTC(q.y, q.m - 1, q.d)).getUTCDay()]}, ${data}`;
  };

  // ---- clínicas, no mesmo período dos indicadores --------------------------
  const serieKey = cfg.periodo.serie;
  const todas = (dados.clinicas || [])
    .map((c) => {
      const a = acumular(c, atual, serieKey);
      const b = acumular(c, anterior, serieKey);
      return { nome: c.nome, usuarios: c.usuarios, ...a, docsAnterior: b.docs };
    })
    .filter((c) => c.docs > 0)
    .sort((x, y) => y.docs - x.docs);

  const clinicas = verTodasClinicas ? todas : todas.slice(0, 6);
  const maxClin = Math.max(1, ...clinicas.map((c) => c.docs));

  // ---- previstos, adesão e projeção ----------------------------------------
  const comProntuai = dados.clinicas_com_prontuai ?? [];
  const semProntuaiBruto = dados.clinicas_sem_prontuai ?? [];
  // Os dois vêm null juntos do back-end. Checar os dois mesmo assim: um back-end
  // anterior a `clinicas_com_prontuai` devolveria só a lista antiga, e aí a
  // tabela de adesão sairia vazia com a projeção dizendo base zero — pior que
  // não mostrar nada.
  const temBrnet = dados.clinicas_sem_prontuai !== null && dados.clinicas_com_prontuai !== null;

  /** Previsões de um credenciado que caem na janela para frente. */
  // Sem `gerado_em` não há "hoje" confiável, e sem ele o teto de um mês que a
  // issue exige não pode ser aplicado. Antes esta função deixava passar TODA
  // previsão nesse caso — o oposto do critério. Agora não passa nenhuma: não
  // mostrar previsto é seguro, mostrar previsto sem recorte não é.
  const diasNaJanela = (c: CredenciadoPrevisto) =>
    temJanela ? c.previsoes.filter((x) => x.data >= hojeISO && x.data <= fimJanelaISO) : [];
  const somaDias = (dias: PrevisaoDia[]) => dias.reduce((a, x) => a + x.pedidos, 0);

  // ---- "Quem vale a pena incluir": ranking por média semanal --------------
  // Média das últimas SEMANAS_MEDIA semanas fechadas, com os zeros contados —
  // sem os zeros, a clínica que liberou 400 numa semana e nada nas outras onze
  // apareceria com 400 por semana.
  //
  // Média e não mediana: decisão de produto (14/10/2026), para a tela falar a
  // mesma língua de quem a lê. A mediana foi medida e descartada; ela derrubaria
  // sozinha a clínica de pico único, mas o fluxo pedido é outro — ranquear,
  // desconfiar, clicar e conferir no gráfico. Quem denuncia o pico, então, é a
  // marca de PICO e as colunas fora do ritmo, não a ordem da lista.
  //
  // Janela fixa para todo mundo — comparar clínicas exige o mesmo denominador.
  const SEMANAS_MEDIA = 12;
  const semanaAtualISO = temJanela ? semanaDe(hojeISO) : "";
  const semanasRecentes = temJanela
    ? Array.from({ length: SEMANAS_MEDIA }, (_, k) => maisDias(semanaAtualISO, -7 * (k + 1))).reverse()
    : [];

  const media = (valores: number[]) =>
    valores.length ? valores.reduce((a, n) => a + n, 0) / valores.length : 0;

  const linhasForaBruto = semProntuaiBruto.map((c) => {
    const semanal = c.liberacoes_semana ?? {};
    const recentes = semanasRecentes.map((w) => semanal[w] ?? 0);
    const med = media(recentes);
    const dias = diasNaJanela(c);
    const previstos = somaDias(dias);
    // Quanto a média faria esperar no mesmo número de dias da janela. Mais
    // que o dobro disso é o "boom" — e o painel que abre mostra se ele é
    // mesmo um evento isolado.
    const esperado = (med * diasJanela) / 7;
    return {
      c,
      dias,
      previstos,
      media: med,
      recentes,
      semanal,
      total: recentes.reduce((a, n) => a + n, 0),
      semanasAtivas: recentes.filter((n) => n > 0).length,
      esperado,
      picoPrevisto: previstos >= 5 && previstos > 2 * esperado,
    };
  });

  // Entra quem tem histórico OU previsto: sem nenhum dos dois não há o que
  // ranquear nem o que incluir.
  const linhasSemProntuai = linhasForaBruto.filter((l) => l.total > 0 || l.previstos > 0);
  const maiorMedia = Math.max(1, ...linhasSemProntuai.map((l) => l.media));

  // Eixo do histórico no modal: toda semana da primeira liberação buscada até a
  // semana corrente, contínuo e igual para todo credenciado. O back-end só manda
  // as semanas com liberação; desenhar só elas encostava três semanas soltas
  // como se fossem seguidas, e o pico isolado — justamente o que o gráfico
  // existe para denunciar — parecia ritmo.
  const semanasHistorico = (() => {
    let inicio = "";
    let fim = semanaAtualISO;
    for (const c of semProntuaiBruto) {
      for (const w in c.liberacoes_semana ?? {}) {
        if (!inicio || w < inicio) inicio = w;
        if (!fim || w > fim) fim = w;
      }
    }
    const semanas: string[] = [];
    if (!inicio) return semanas;
    for (let w = inicio; w <= fim; w = maisDias(w, 7)) semanas.push(w);
    return semanas;
  })();
  const naJanelaMedia = new Set(semanasRecentes);

  // ---- "Quem está usando pouco": previsto × expedido, por semana fechada ---
  // O indicador que a tabela de adesão tentava ser. A diferença é a janela:
  // aqui a linha inteira fala de UMA semana — o que foi prometido nela e o que
  // aconteceu com cada um daqueles pedidos. A tabela antiga punha previsto do
  // futuro ao lado de realizado do passado, e quem batia o olho lia a divisão
  // de um pelo outro, que não existia.
  //
  // Toda a conta vem de `desfecho_previsao_semana`, montada no back-end pedido
  // a pedido. Aqui só se agrupa e ordena: nenhuma razão nova é inventada.
  const usoSemanal: UsoSemanal | null = (() => {
    if (!temBrnet || !temJanela) return null;
    // Sem a data em que a ligação por pedido começou não dá para saber em que
    // semana "passou pelo ProntuAI" vira medida confiável — e o indicador
    // inteiro é sobre isso.
    const desde = dados.expedicoes_desde;
    if (!desde) return null;

    const semanaAtual = semanaDe(hojeISO);
    const chaves = new Set<string>();
    comProntuai.forEach((c) =>
      Object.keys(c.desfecho_previsao_semana ?? {}).forEach((s) => {
        // Fechada e inteiramente dentro do período com ligação por pedido.
        if (s < semanaAtual && s >= desde) chaves.add(s);
      }),
    );
    if (!chaves.size) return null;

    const semanas = [...chaves]
      .sort()
      .reverse()
      .map((iso) => {
        const linhas: LinhaUsoSemana[] = [];
        comProntuai.forEach((c) => {
          const t = c.desfecho_previsao_semana?.[iso];
          if (!t) return;
          const [viaProntuai, fora, naoLiberado] = t;
          const previstos = viaProntuai + fora + naoLiberado;
          // Clínica sem previsão naquela semana não tem o que reconciliar —
          // fica fora da lista em vez de entrar como uma linha de zeros.
          if (!previstos) return;
          const adesao = (viaProntuai / previstos) * 100;
          const clinica = c.clinica ?? c.nome;
          linhas.push({
            clinica,
            local: c.cidade && c.uf ? `${c.cidade}/${c.uf}` : "—",
            previstos,
            viaProntuai,
            fora,
            naoLiberado,
            adesao,
            adesaoLabel: num(adesao),
            adesaoColor: adesao >= 90 ? POS : adesao >= 75 ? CORES.alerta : NEG,
            pctVia: pct(viaProntuai, previstos),
            pctFora: pct(fora, previstos),
            pctNao: pct(naoLiberado, previstos),
            tip:
              `${clinica} — ${fmt(previstos)} previstos na semana: ${fmt(viaProntuai)} pela plataforma, ` +
              `${fmt(fora)} liberados por fora, ${fmt(naoLiberado)} ainda não liberados`,
          });
        });
        // Ordem padrão: pelo volume ABSOLUTO que escapou da plataforma, não
        // pela taxa. 30% de 10 pedidos não é alvo de visita; 15% de 400 é.
        linhas.sort((a, b) => b.fora - a.fora || b.previstos - a.previstos);

        const soma = (f: (l: LinhaUsoSemana) => number) => linhas.reduce((a, l) => a + f(l), 0);
        const previstos = soma((l) => l.previstos);
        const viaProntuai = soma((l) => l.viaProntuai);
        const adesao = pct(viaProntuai, previstos);
        return {
          iso,
          label: intervaloSemana(iso),
          linhas,
          previstos,
          viaProntuai,
          fora: soma((l) => l.fora),
          naoLiberado: soma((l) => l.naoLiberado),
          adesao,
          adesaoLabel: num(adesao),
        };
      });

    // Nada de projeção aqui: este indicador é do passado inteiro. O futuro é o
    // outro, e misturar os dois foi o que fez a projeção virar um card.
    return { semanas };
  })();

  // Ordem padrão: média desc, desempatando pelo volume total da janela. As
  // duas colunas são do mesmo histórico, então o desempate não troca de
  // grandeza no meio do ranking.
  const linhasForaRanqueadas: LinhaForaProntuai[] = linhasSemProntuai
    .slice()
    .sort((a, b) => b.media - a.media || b.total - a.total)
    .map((l) => {
      const { c, dias } = l;
      const foraDaJanela = c.pedidos_previstos - l.previstos;
      // A série do modal mostra o histórico INTEIRO, não só as 12 semanas da
      // média: a pergunta que ele responde é "isso é comportamento ou foi
      // uma semana?", e cortar o histórico esconderia justamente a resposta.
      const porSemana = c.liberacoes_semana ?? {};
      const serie = () => semanasHistorico.map((w) => {
        const liberacoes = porSemana[w] ?? 0;
        const pico = liberacoes > 2 * l.media && liberacoes >= l.media + 3;
        const parcial = w === semanaAtualISO;
        return {
          iso: w,
          label: rotuloSemana(w),
          liberacoes,
          pico,
          naMedia: naJanelaMedia.has(w),
          parcial,
          tip:
            `${intervaloSemana(w)} — ${fmt(liberacoes)} ${liberacoes === 1 ? "liberação" : "liberações"}` +
            (parcial ? " até agora, semana em andamento" : "") +
            (pico ? ` · acima do ritmo dela (média ${umDecimal(l.media)})` : ""),
        };
      });
      return {
        credenciado: c.credenciado,
        name: c.nome,
        local: c.cidade && c.uf ? `${c.cidade}/${c.uf}` : "—",
        media: l.media,
        mediaLabel: umDecimal(l.media),
        total: l.total,
        semanasAtivas: l.semanasAtivas,
        regularidade: pct(l.semanasAtivas, SEMANAS_MEDIA),
        regularidadeLabel: `${l.semanasAtivas}/${SEMANAS_MEDIA}`,
        pct: pct(l.media, maiorMedia),
        previstos: l.previstos,
        picoPrevisto: l.picoPrevisto,
        esperado: l.esperado,
        esperadoLabel: umDecimal(l.esperado),
        serie,
        proxima: dias.length ? dataCurta(dias[0].data) : "—",
        proximaISO: dias.length ? dias[0].data : "",
        datas: dias.map((x) => ({ label: rotuloPrevisao(x.data), pedidos: fmt(x.pedidos), n: x.pedidos })),
        vencidos: c.vencidos,
        depoisDaJanela: foraDaJanela,
        documentos: c.documentos,
        tip:
          `${c.nome} — média de ${umDecimal(l.media)} liberações por semana em ` +
          `${l.semanasAtivas} das últimas ${SEMANAS_MEDIA} semanas (${fmt(l.total)} no total)`,
      };
    });

  // A semana que serve de premissa ao simulador: a última fechada medida no
  // indicador de cima. O simulador não inventa adesão nenhuma — usa a que
  // acabou de ser mostrada na tela, e diz de qual semana ela veio.
  const ultimaSemana = usoSemanal?.semanas[0] ?? null;

  // ---- acurácia: mesma janela de período e de gráfico da utilização --------
  const accP = dados.acuracia?.[cfg.periodo.serie] ?? [];
  const accAtual = np ? accP.slice(-np) : accP.slice();
  const accAnterior = np
    ? accP.slice(Math.max(0, accP.length - 2 * np), Math.max(0, accP.length - np))
    : [];
  const accG = dados.acuracia?.[cfg.grafico.serie] ?? [];
  const accGrafico = cfg.grafico.n ? accG.slice(-cfg.grafico.n) : accG.slice();

  // acerto = concordância direta + divergência resolvida por motivo externo
  const acertosDe = (arr: PontoAcuracia[]) =>
    soma(arr, "ok_aprovou") +
    soma(arr, "ok_rejeitou") +
    soma(arr, "div_aprovou_jeitinho") +
    soma(arr, "div_rejeitou_jeitinho");
  const baseDe = (arr: PontoAcuracia[]) =>
    soma(arr, "ok_aprovou") + soma(arr, "ok_rejeitou") + soma(arr, "div_aprovou") + soma(arr, "div_rejeitou");

  const acertos = acertosDe(accAtual);
  const baseAcc = baseDe(accAtual);
  const acuracia = pct(acertos, baseAcc);
  const acuraciaAnt = baseDe(accAnterior) ? pct(acertosDe(accAnterior), baseDe(accAnterior)) : null;

  const concordanciaDireta = soma(accAtual, "ok_aprovou") + soma(accAtual, "ok_rejeitou");
  const jeitinhoTotal = soma(accAtual, "div_aprovou_jeitinho") + soma(accAtual, "div_rejeitou_jeitinho");
  // Contas por janela: o valor do card e o delta dele precisam medir a MESMA
  // grandeza. Antes o delta comparava só uma parcela (div_aprovou bruto,
  // falha_aprovou) e divergia do número exibido.
  const riscoRealDe = (arr: PontoAcuracia[]) =>
    soma(arr, "div_aprovou") - soma(arr, "div_aprovou_jeitinho");
  // A falha aprovada por CNPJ de outra empresa ou atendimento ainda fora do
  // BRNET não é da IA — o dado de fora é que não batia — e sai da conta.
  const falhasDe = (arr: PontoAcuracia[]) =>
    soma(arr, "falha_rejeitou") + soma(arr, "falha_aprovou") - soma(arr, "falha_externa");
  const falhaExterna = soma(accAtual, "falha_externa");
  const riscoReal = riscoRealDe(accAtual);
  const divRejeitou = soma(accAtual, "div_rejeitou") - soma(accAtual, "div_rejeitou_jeitinho");
  const falhasTecnicas = falhasDe(accAtual);

  const varAcc = (conta: (arr: PontoAcuracia[]) => number) => {
    if (!comparavel) return "";
    const a = conta(accAtual);
    const b = conta(accAnterior);
    if (!b) return a ? "novo" : "";
    return `${a >= b ? "+" : "-"}${Math.abs(((a - b) / b) * 100).toFixed(0)}%`;
  };

  const alturaAcc = (v: number) => Math.max(3, Math.round(((v - PISO_ACC) / (100 - PISO_ACC)) * 200));

  const situacoes: [string, number, boolean, string][] = [
    ["IA aprovou → humano aprovou", soma(accAtual, "ok_aprovou"), true, CORES.positivo],
    ["IA rejeitou → humano rejeitou", soma(accAtual, "ok_rejeitou"), true, CORES.petroleo],
    ["Divergência resolvida por motivo externo", jeitinhoTotal, true, CORES.agua],
    ["IA rejeitou → humano aprovou", divRejeitou, false, CORES.alerta],
    ["IA aprovou → humano rejeitou", riscoReal, false, CORES.negativo],
  ];

  // ---- por que a acurácia não está maior -----------------------------------
  const fatores: [string, number, string][] = (
    [
      ["Exame faltante que a IA não detectou", soma(accAtual, "mot_exame_nao_detectado"), CORES.negativo],
      ["IA não reconheceu exame que estava no PDF", soma(accAtual, "mot_matching_ia"), CORES.alerta],
      ["Regra formal que a IA ainda não verifica", soma(accAtual, "mot_regra_formal"), CORES.agua],
      // Inclui o campo em branco e o motivo sem conteúdo de causa ("ok",
      // "prontuário correto"). Os dois dizem a mesma coisa: houve divergência e
      // não se sabe por quê. Ver `dashboard_indicadores.sql`.
      ["Revisor não informou a causa", soma(accAtual, "mot_sem_justificativa"), "#9AA9B3"],
      ["Outros motivos", soma(accAtual, "mot_outro"), "#BFC3C6"],
    ] as [string, number, string][]
  )
    .filter((f) => f[1] > 0)
    .sort((a, b) => b[1] - a[1]);

  // Divergências resolvidas por motivo externo, pelo código do parecer. Não
  // derrubam a acurácia — contam como acerto —, mas dizem por que a decisão
  // mudou. Rótulos do próprio modal, para quem lê reconhecer a opção.
  const CAMPO_MOTIVO_EXTERNO: Record<MotivoExterno, keyof PontoAcuracia> = {
    EXAME_POR_FORA: "ext_exame_por_fora",
    GUIA_NAO_ANEXADA: "ext_guia_nao_anexada",
    CNPJ_DIVERGENTE: "ext_cnpj_divergente",
    ATENDIMENTO_NAO_REGISTRADO: "ext_atendimento_nao_registrado",
    OUTRO_TICKET: "ext_outro_ticket",
    CLIENTE_AUTORIZOU: "ext_cliente_autorizou",
    OUTRO: "ext_outro",
  };
  const motivosExternos = [
    ...MOTIVOS_EXTERNOS.map((m) => ({ name: m.rotulo, count: soma(accAtual, CAMPO_MOTIVO_EXTERNO[m.codigo]) })),
    { name: "Justificativa escrita antes do modal", count: soma(accAtual, "ext_sem_codigo") },
  ]
    .filter((m) => m.count > 0)
    .sort((a, b) => b.count - a.count);

  const totalFatores = fatores.reduce((a, f) => a + f[1], 0);
  const maiorFator = fatores.length ? fatores[0] : null;
  const semJustDiv = soma(accAtual, "sem_just_divergencia");
  // A classificação por motivo só existe se a extração trouxe os campos mot_*.
  const temMotivos = accAtual.some((p) => p.mot_exame_nao_detectado !== undefined);

  return {
    rangeLabel: nomePeriodo(cfg.periodo.serie, atual),
    compareLabel: comparar
      ? comparavel
        ? nomePeriodo(cfg.periodo.serie, anterior)
        : np === 0
          ? "toda a base"
          : "sem período anterior completo"
      : "nenhum período",

    chipPeriodo:
      cfg.grafico.serie === "semanal"
        ? `Últimas ${grafico.length} semanas`
        : cfg.grafico.n
          ? `Últimos ${grafico.length} meses`
          : "Toda a base",

    // Gráficos usam a série de contexto (mais pontos que o período dos KPIs).
    graficoLegenda:
      cfg.grafico.serie === "semanal"
        ? `Últimas ${grafico.length} semanas`
        : cfg.grafico.n
          ? `Últimos ${grafico.length} meses`
          : "Toda a base, por mês",

    kpiPrimary: [
      kpi("Envios realizados", fmt(enviados), variacao("docs"), "up", nomePeriodo(cfg.periodo.serie, atual)),
      kpi(
        "Análises realizadas",
        fmt(revisados),
        variacao("revisados"),
        "up",
        // O número é só de decisão humana; o rótulo diz de quem, para não ser
        // lido como documento que a IA analisou.
        `decisões do time BR MED · ${num(pct(revisados, enviados))} do que foi enviado`,
      ),
      kpi(
        "Análises pendentes",
        fmt(pendentes),
        variacaoPendentes(),
        // Subir é piorar: mais prontuário chegou sem passar pelo time. Atenção
        // ao ler: o período atual ainda está em análise e o anterior já teve
        // dias de revisão, então a variação tende a sair alta — em 22/10 deu
        // +134% na semana com a fila igual (211 × 214) no mesmo ponto das duas.
        "down",
        `${fmt(comFaltante)} com exame faltante · ${num(pct(pendentes, enviados))} do que foi enviado`,
      ),
    ],

    docsSeries: grafico.map((p) => ({
      month: rotuloG(p.chave),
      value: p.docs,
      h: bar(p.docs, maxDocs, 236),
      tip: p.docs
        ? `${rotuloG(p.chave)} — ${fmt(p.docs)} enviados: ${fmt(p.validados)} aprovados, ${fmt(p.rejeitados)} rejeitados, ${fmt(p.pendentes)} com exame faltante`
        : `${rotuloG(p.chave)} — sem documentos`,
    })),

    // Cobertura do ProntuAI sobre as expedições da empresa, ponto a ponto.
    coberturaSeries: (() => {
      const pontos = grafico.map((p) => {
        const a = partes(p.chave);
        let ini = new Date(Date.UTC(a.y, a.m - 1, a.d));
        if (inicioCobertura && ini < inicioCobertura) ini = inicioCobertura;
        const fim =
          cfg.grafico.serie === "semanal"
            ? new Date(Date.UTC(a.y, a.m - 1, a.d + 6))
            : new Date(Date.UTC(a.y, a.m, 0));
        const emp = expedicoesEmpresa(ini, fim);
        const lib = expedicoesEntre(viaPorDia, ini, fim, ultimoDoc);
        const v = emp ? (lib / emp) * 100 : 0;
        return { mes: rotuloG(p.chave), v, emp, lib };
      });
      const maxV = Math.max(10, ...pontos.map((p) => p.v));
      return pontos.map((p) => ({
        month: p.mes,
        label: p.emp ? num(p.v) : "—",
        h: p.emp ? Math.max(3, Math.round((p.v / maxV) * 190)) : 0,
        tip: p.emp
          ? `${p.mes} — ${fmt(p.lib)} de ${fmt(p.emp)} expedições (${num(p.v)})`
          : `${p.mes} — sem expedições registradas`,
      }));
    })(),

    prazoClinica: graficoPrazo(dados.prazo_clinica_dia || {}, ["envio", "envios"]),
    prazoTecnico: graficoPrazo(dados.prazo_tecnico_dia || {}, ["liberação", "liberações"]),

    ranking: clinicas.map((c, i) => {
      const v = !comparavel
        ? ""
        : c.docsAnterior
          ? `${c.docs >= c.docsAnterior ? "+" : "-"}${Math.abs(((c.docs - c.docsAnterior) / c.docsAnterior) * 100).toFixed(0)}%`
          : c.docs
            ? "novo"
            : "";
      const comp = !comparavel ? "" : ` (antes: ${fmt(c.docsAnterior)})`;
      return {
        name: c.nome,
        docs: c.docs,
        pct: Math.round(pct(c.docs, maxClin)),
        color: CORES_RANK[i] || CORES.agua,
        delta: comparar ? v : "",
        deltaColor: v.startsWith("-") ? NEG : POS,
        tip: `${c.nome} — ${fmt(c.docs)} enviados${comp}, ${fmt(c.revisados)} analisados pelo time, ${fmt(c.validados)} aprovados`,
      };
    }),

    totalClinicas: todas.length,

    foraProntuai: temBrnet
      ? linhasForaRanqueadas
      : null,
    janelaPrevistos: temJanela
      ? `de hoje a ${dataCurta(fimJanelaISO)} · ${diasJanela} dias`
      : "sem data de referência do back-end — previstos indisponíveis",
    janelaMedia: semanasRecentes.length
      ? `${dataCurta(semanasRecentes[0])} a ${dataCurta(maisDias(semanasRecentes[semanasRecentes.length - 1], 6))}`
      : "—",

    periodoLabel: nomePeriodo(cfg.periodo.serie, atual),
    usoSemanal,

    simulador: ultimaSemana
      ? {
          viaProntuaiSemana: ultimaSemana.viaProntuai,
          adesao: ultimaSemana.adesao,
          semana: ultimaSemana.label,
        }
      : null,

    kpisAcuracia: [
      kpiAcc(
        "Acurácia",
        baseAcc ? num(acuracia) : "—",
        comparavel ? pp(acuracia, acuraciaAnt) : "",
        "up",
        `${fmt(acertos)} de ${fmt(baseAcc)} documentos revisados`,
      ),
      kpiAcc(
        "Concordância direta",
        baseAcc ? num(pct(concordanciaDireta, baseAcc)) : "—",
        comparavel && baseDe(accAnterior)
          ? pp(
              pct(concordanciaDireta, baseAcc),
              pct(soma(accAnterior, "ok_aprovou") + soma(accAnterior, "ok_rejeitou"), baseDe(accAnterior)),
            )
          : "",
        "up",
        `${fmt(concordanciaDireta)} sem necessidade de ressalva`,
      ),
      kpiAcc(
        "Aprovações derrubadas",
        fmt(riscoReal),
        varAcc(riscoRealDe),
        "down",
        "IA liberou e o revisor barrou — é o risco real",
      ),
      kpiAcc(
        "Falhas técnicas",
        fmt(falhasTecnicas),
        varAcc(falhasDe),
        "down",
        falhaExterna
          ? `não leu CPF/CNPJ · sem ${fmt(falhaExterna)} de CNPJ ou atendimento de fora`
          : "não leu CPF/CNPJ · fora da conta de acurácia",
      ),
    ],

    acuraciaSeries: accGrafico.map((p) => {
      const ac = p.ok_aprovou + p.ok_rejeitou + p.div_aprovou_jeitinho + p.div_rejeitou_jeitinho;
      const bs = p.ok_aprovou + p.ok_rejeitou + p.div_aprovou + p.div_rejeitou;
      const v = bs ? (ac / bs) * 100 : 0;
      return {
        month: rotuloG(p.chave),
        label: bs ? num(v) : "—",
        h: bs ? alturaAcc(v) : 0,
        tip: bs
          ? `${rotuloG(p.chave)} — ${fmt(ac)} acertos de ${fmt(bs)} revisados`
          : `${rotuloG(p.chave)} — sem revisões no período`,
      };
    }),

    fatorPrincipal: !temMotivos
      ? "Classificação de motivos indisponível nesta extração."
      : maiorFator
        ? `${maiorFator[0]} — ${fmt(maiorFator[1])} de ${fmt(totalFatores)} divergências (${Math.round(pct(maiorFator[1], totalFatores))}%)`
        : "Nenhuma divergência no período.",

    penteFino: fatores.map(([name, count, color]) => ({
      name,
      count,
      color,
      pct: Math.round(pct(count, maiorFator ? maiorFator[1] : 1)),
      tip: `${name} — ${fmt(count)} casos, ${Math.round(pct(count, totalFatores))}% das divergências`,
    })),

    motivosExternos,
    motivosExternosTotal: jeitinhoTotal,

    notaSemJustificativa: !temMotivos
      ? "Rode a versão atualizada da consulta para trazer a classificação dos motivos e a contagem de decisões sem justificativa."
      : semJustDiv
        ? `Em ${fmt(semJustDiv)} decisões o revisor contrariou a IA sem registrar o motivo — nesses casos não dá para saber se houve erro da IA ou razão externa. O campo passou a ser obrigatório recentemente, então a cobertura melhora daqui em diante.`
        : "Todas as decisões contrárias à IA no período têm justificativa registrada.",

    porTipo: situacoes.map(([name, count, acerto, cor]) => ({
      name,
      vol: fmt(count),
      acc: baseAcc ? num(pct(count, baseAcc)) : "—",
      classificacao: acerto ? "Acerto" : "Divergência",
      classificacaoColor: acerto ? POS : NEG,
      peso: Math.round(pct(count, Math.max(1, ...situacoes.map((s) => s[1])))),
      cor,
    })),

    acuraciaExame: (() => {
      const fonte = dados.acuracia_exames;
      if (!fonte) return null;
      const blocos = fonte.series?.[cfg.periodo.serie] ?? {};

      // Soma pelos MESMOS pontos do período dos outros indicadores: as chaves
      // são as da série principal (segunda-feira da semana, dia 1 do mês).
      type ContaExame = { n: number; motivos: Map<string, number>; casos: CasoErroExame[] };
      const errosDe = (e: ContaExame) => [...e.motivos.values()].reduce((s, v) => s + v, 0);

      const somar = (pontos: PontoSerie[]) => {
        let pareceres = 0;
        let comParecer = 0;
        let decisoes = 0;
        const exames = new Map<string, ContaExame>();
        const conta = (nome: string) => {
          const e: ContaExame = exames.get(nome) ?? { n: 0, motivos: new Map(), casos: [] };
          exames.set(nome, e);
          return e;
        };
        const anotar = (e: ContaExame, motivo: string, casos: number) => {
          if (casos) e.motivos.set(motivo, (e.motivos.get(motivo) ?? 0) + casos);
        };
        for (const p of pontos) {
          const b = blocos[p.chave];
          if (!b) continue;
          pareceres += b.pareceres;
          comParecer += b.com_parecer;
          decisoes += b.decisoes;
          for (const [nome, [n, motivos, presenca]] of Object.entries(b.exames)) {
            const e = conta(nome);
            e.n += n;
            if (typeof motivos === "number") {
              // Back-end anterior aos motivos: só falta e presença indevidas.
              anotar(e, "FALTANTE_INCORRETO", motivos);
              anotar(e, "ENCONTRADO_INCORRETO", presenca ?? 0);
            } else {
              for (const [categoria, casos] of Object.entries(motivos)) anotar(e, categoria, casos);
            }
          }
          for (const caso of b.casos ?? []) conta(caso.exame).casos.push(caso);
        }
        let avaliacoes = 0;
        let erros = 0;
        exames.forEach((e) => {
          avaliacoes += e.n;
          erros += errosDe(e);
        });
        const acuracia = avaliacoes ? ((avaliacoes - erros) / avaliacoes) * 100 : null;
        return { pareceres, comParecer, decisoes, exames, avaliacoes, erros, acuracia };
      };

      const agora = somar(atual);
      const antes = comparavel ? somar(anterior) : null;

      // Pré-ordenadas por volume e depois por erros: a tela ordena pela menor
      // acurácia com sort estável, então no empate vem primeiro o que mais erra
      // e, persistindo, o mais frequente.
      const todas = [...agora.exames.entries()].sort(([, a], [, b]) => b.n - a.n);
      const doMinimo = todas.filter(([, e]) => e.n >= MINIMO_AVALIACOES_EXAME);
      const poucos = todas.filter(([, e]) => e.n < MINIMO_AVALIACOES_EXAME && errosDe(e) > 0);
      // A barra é a TAXA de erro, na escala do exame que mais erra: com a
      // acurácia toda perto de 100%, uma barra de acurácia sairia cheia em
      // todas as linhas.
      const maiorTaxa = Math.max(0, ...doMinimo.map(([, e]) => errosDe(e) / e.n)) || 1;
      const vezes = (n: number, um: string, varios: string) => `${fmt(n)} ${n === 1 ? um : varios}`;

      const rotulo = (categoria: string) => ROTULO_MOTIVO[categoria] ?? "Outro";
      const linhaDe = ([exame, e]: [string, ContaExame]): LinhaAcuraciaExame => {
        const erros = errosDe(e);
        const acuracia = ((e.n - erros) / e.n) * 100;
        const motivos = [...e.motivos.entries()]
          .sort(([, a], [, b]) => b - a)
          .map(([categoria, casos]) => ({ rotulo: rotulo(categoria), contexto: CONTEXTO_MOTIVO[categoria] ?? "", casos }));
        return {
          exame,
          documentos: e.n,
          erros,
          pctErro: Math.min(100, (erros / e.n / maiorTaxa) * 100),
          motivos,
          casos: [...e.casos]
            .sort((a, b) => b.enviado.localeCompare(a.enviado))
            .map((c) => ({
              documento: c.documento,
              clinica: c.clinica,
              enviadoLabel: `${c.enviado.slice(8, 10)}/${c.enviado.slice(5, 7)}`,
              motivo: rotulo(c.motivo),
            })),
          acuracia,
          acuraciaLabel: num(acuracia),
          tip: `${exame} — ${vezes(e.n, "exame", "exames")}, ${vezes(erros, "erro", "erros")}`,
        };
      };
      const porErros = (a: LinhaAcuraciaExame, b: LinhaAcuraciaExame) => b.erros - a.erros;
      const linhas = doMinimo.map(linhaDe).sort(porErros).sort((a, b) => a.acuracia - b.acuracia);
      const poucosCasos = poucos.map(linhaDe).sort(porErros);

      const acuraciaLabel = agora.acuracia === null ? "—" : num(agora.acuracia);
      return {
        kpi: kpiAcc(
          "Acurácia por exame",
          acuraciaLabel,
          antes && agora.acuracia !== null && antes.acuracia !== null ? pp(agora.acuracia, antes.acuracia) : "",
          "up",
          agora.avaliacoes
            ? `${fmt(agora.avaliacoes)} exames em ${fmt(agora.pareceres)} pareceres`
            : "nenhum parecer no período",
        ),
        linhas,
        poucosCasos,
        minimo: MINIMO_AVALIACOES_EXAME,
        abaixoDoMinimo: agora.exames.size - doMinimo.length - poucos.length,
        avaliacoes: agora.avaliacoes,
        erros: agora.erros,
        pareceres: agora.pareceres,
        decisoes: agora.decisoes,
        adesaoLabel: agora.decisoes ? num(pct(agora.comParecer, agora.decisoes)) : null,
        acuraciaLabel,
        periodoLabel: nomePeriodo(cfg.periodo.serie, atual),
      };
    })(),
  };
}
