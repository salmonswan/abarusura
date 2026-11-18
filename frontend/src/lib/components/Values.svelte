<script lang="ts">
  const values = ['Discipline', 'Integrity', 'Determination', 'Dedication', 'Diligence']
</script>

<ul class="values cond" aria-label="Club values">
  {#each values as value}
    <li>{value}</li>
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
