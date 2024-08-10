class KanbanBoard {
  constructor(element, taskMovedCallback) {
    this.element = element;
    this.taskMovedCallback = taskMovedCallback;

    this.lists = element.querySelectorAll(".kanban-cards");

    this.lists.forEach((list) => {
      Sortable.create(list, {
        group: "kanban",
        animation: 150,
        onEnd: function (event) {
          const from = event.from.closest(".kanban-list").id;
          const to = event.to.closest(".kanban-list").id;
          const taskId = event.item.dataset.id;
          const newOrder = Array.from(event.to.children).map((el, index) => ({
            id: el.dataset.id,
            order: index + 1,
          }));

          taskMovedCallback(taskId, from, to, newOrder);
        },
      });
    });
  }
}

window.Hooks = window.Hooks ?? {};

window.Hooks.KanbanBoard = {
  mounted() {
    console.log("KanbanBoard mounted");
    this.kanban = new KanbanBoard(this.el, (taskId, from, to, order) => {
      this.pushEvent("task-moved", { taskId, from, to, order });
    });
  },
};
