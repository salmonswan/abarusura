<script lang="ts">
  import { onMount } from 'svelte'
  const values = ['Discipline', 'Integrity', 'Determination', 'Dedication', 'Diligence']
  let band: HTMLUListElement
  let lit = $state(values.length)
  let revealing = $state(false)

  onMount(() => {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return
    lit = 0
    let timer: number | undefined
    const observer = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return
      observer.disconnect()
      revealing = true
      timer = window.setTimeout(lightNext, 250)
    })

    function lightNext() {
      lit += 1
      if (lit < values.length) timer = window.setTimeout(lightNext, 250)
    }

    observer.observe(band)
    return () => {
      observer.disconnect()
      window.clearTimeout(timer)
    }
  })
</script>

<ul class="values cond" class:revealing bind:this={band} aria-label="Club values">
  {#each values as value, index}
    <li class:unlit={index >= lit}>{value}</li>
  {/each}
</ul>

<style>
  .values {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-around;
    gap: 20px 32px;
    margin: 0;
    padding: 30px 24px;
    list-style: none;
    font-size: 24px;
    font-weight: 500;
  }

  li {
    color: var(--white);
  }

  li:global(.unlit) {
    color: #6f7799;
  }
</style>
