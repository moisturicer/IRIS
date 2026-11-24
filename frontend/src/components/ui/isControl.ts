/** Whether a press landed on something with its own job, not on a panel's empty space (IR-1306). */
export function isControl(target: EventTarget | null): boolean {
  return target instanceof Element
    && !!target.closest("a,button,input,textarea,select,label,[role=button],[role=menu],[role=menuitem],[role=separator]");
}
