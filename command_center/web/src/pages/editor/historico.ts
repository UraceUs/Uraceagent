/* Editor do site como o Canva (#315): desfazer e refazer. Uma pilha de fotos da página (até 100 passos). A
 * digitação seguida no mesmo lugar vira um passo só: a mesma `chave` com menos de 800 ms entre uma tecla e outra. */
export class Historico<T> {
  private passado: T[] = []
  private futuro: T[] = []
  private chave = ''
  private quando = 0
  static readonly MAX = 100
  static readonly JUNTA_MS = 800

  /** Antes de mudar: guarda como estava (`antes`). */
  registrar(antes: T, chave = '') {
    const agora = Date.now()
    if (chave && chave === this.chave && agora - this.quando < Historico.JUNTA_MS) { this.quando = agora; return }
    this.passado.push(antes)
    if (this.passado.length > Historico.MAX) this.passado.shift()
    this.futuro = []
    this.chave = chave
    this.quando = agora
  }
  desfazer(atual: T): T | null {
    const x = this.passado.pop()
    if (x === undefined) return null
    this.futuro.push(atual)
    this.chave = ''
    return x
  }
  refazer(atual: T): T | null {
    const x = this.futuro.pop()
    if (x === undefined) return null
    this.passado.push(atual)
    this.chave = ''
    return x
  }
  /** Fecha o passo da digitação (sair do texto, clicar em outra coisa). */
  cortar() { this.chave = '' }
  limpar() { this.passado = []; this.futuro = []; this.chave = '' }
  get podeDesfazer() { return this.passado.length > 0 }
  get podeRefazer() { return this.futuro.length > 0 }
}
